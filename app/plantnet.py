from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from . import store
from .config import settings as env_settings

log = logging.getLogger("plants.plantnet")

VALID_ORGANS = {"auto", "leaf", "flower", "fruit", "bark"}


class PlantNetError(Exception):
    """Raised when Pl@ntNet cannot be reached or the request is rejected."""


class PlantNetClient:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def _setting(self, key: str, fallback: str) -> str:
        if self.db is not None:
            value = store.get_value(self.db, key, fallback)
            return value or fallback
        return getattr(env_settings, key, fallback) or fallback

    @property
    def api_key(self) -> str:
        return self._setting("plantnet_api_key", env_settings.plantnet_api_key)

    async def identify(
        self,
        image: bytes,
        filename: str = "photo.jpg",
        organ: str = "auto",
        project: str | None = None,
        lang: str | None = None,
        nb_results: int = 5,
    ) -> dict:
        api_key = self.api_key
        if not api_key:
            raise PlantNetError(
                "Pl@ntNet API key is not configured. Add it in Settings or set PLANTNET_API_KEY."
            )
        if organ not in VALID_ORGANS:
            organ = "auto"
        project = project or self._setting("plantnet_project", env_settings.plantnet_project)
        lang = lang or self._setting("plantnet_lang", env_settings.plantnet_lang)

        url = f"{env_settings.plantnet_base}/v2/identify/{project}"
        params = {
            "api-key": api_key,
            "lang": lang,
            "nb-results": nb_results,
            "no-reject": "true",
        }
        files = {"images": (filename, image, "image/jpeg")}
        data = {"organs": organ}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, params=params, data=data, files=files)
        except httpx.HTTPError as exc:
            raise PlantNetError(f"Could not reach Pl@ntNet: {exc}") from exc

        if resp.status_code == 401:
            raise PlantNetError("Pl@ntNet rejected the API key (401 Unauthorized).")
        if resp.status_code == 404:
            raise PlantNetError(f"Pl@ntNet project '{project}' was not found (404).")
        if resp.status_code == 429:
            raise PlantNetError("Pl@ntNet daily request quota exceeded (429).")
        if resp.status_code >= 400:
            detail = resp.text[:200]
            raise PlantNetError(f"Pl@ntNet error {resp.status_code}: {detail}")

        return self._parse(resp.json())

    @staticmethod
    def _parse(payload: dict) -> dict:
        candidates = []
        for item in payload.get("results", []):
            species = item.get("species", {})
            common = species.get("commonNames") or []
            candidates.append(
                {
                    "score": round(float(item.get("score", 0.0)), 4),
                    "scientific_name": species.get("scientificNameWithoutAuthor")
                    or species.get("scientificName")
                    or "",
                    "common_names": common,
                    "family": (species.get("family") or {}).get("scientificNameWithoutAuthor"),
                    "genus": (species.get("genus") or {}).get("scientificNameWithoutAuthor"),
                }
            )

        organs = payload.get("predictedOrgans") or []
        predicted_organ = organs[0].get("organ") if organs else None

        return {
            "best_match": payload.get("bestMatch"),
            "predicted_organ": predicted_organ,
            "remaining_requests": payload.get("remainingIdentificationRequests"),
            "candidates": candidates,
        }
