from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from .config import settings as env_settings
from . import store

log = logging.getLogger("plants.ha")


class HAClient:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def _url(self) -> str:
        return env_settings.ha_url

    def _token(self) -> str:
        return env_settings.ha_token

    def _entity(self, key: str) -> str:
        if self.db is not None:
            return store.get_value(self.db, key, "") or ""
        return getattr(env_settings, key, "") or ""

    async def _get_state(self, entity_id: str) -> dict | None:
        if not entity_id:
            return None
        url = f"{self._url()}/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {self._token()}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                log.warning("Entity %s not found in Home Assistant", entity_id)
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("Failed to fetch %s: %s", entity_id, exc)
            return None

    async def get_weather(self) -> dict:
        weather = await self._get_state(self._entity("ha_weather_entity"))
        outdoor = await self._get_state(self._entity("ha_outdoor_temp_entity"))
        indoor = await self._get_state(self._entity("ha_indoor_temp_entity"))
        rain = await self._get_state(self._entity("ha_rain_entity"))

        result: dict = {"available": False}
        if weather:
            attrs = weather.get("attributes", {})
            result.update(
                available=True,
                condition=weather.get("state"),
                temperature=attrs.get("temperature"),
                humidity=attrs.get("humidity"),
                forecast=_forecast_summary(attrs.get("forecast")),
            )
        if outdoor:
            try:
                result["outdoor_temp_c"] = float(outdoor.get("state"))
                result["available"] = True
            except (TypeError, ValueError):
                result["outdoor_temp_c"] = None
        if indoor:
            try:
                result["indoor_temp_c"] = float(indoor.get("state"))
                result["available"] = True
            except (TypeError, ValueError):
                result["indoor_temp_c"] = None
        if rain:
            try:
                result["rain_mm"] = float(rain.get("state"))
            except (TypeError, ValueError):
                result["rain_mm"] = None
        return result

    async def get_all_states(self) -> list[dict]:
        url = f"{self._url()}/api/states"
        headers = {"Authorization": f"Bearer {self._token()}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("Failed to list Home Assistant states: %s", exc)
            return []

    async def get_notify_services(self) -> list[str]:
        url = f"{self._url()}/api/services"
        headers = {"Authorization": f"Bearer {self._token()}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            log.warning("Failed to list Home Assistant services: %s", exc)
            return []
        out: list[str] = []
        for domain in data:
            if domain.get("domain") == "notify":
                for name in domain.get("services", {}):
                    out.append(f"notify.{name}")
        return sorted(out)

    async def call_notify(self, service: str, message: str, title: str) -> bool:
        """Call a notify service, e.g. ``notify.mobile_app_sofia`` or ``notify.telegram``."""
        if "." in service:
            domain, name = service.split(".", 1)
        else:
            domain, name = "notify", service
        url = f"{self._url()}/api/services/{domain}/{name}"
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }
        payload = {"message": message, "title": title}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("Notify via %s failed: %s", service, exc)
            return False


def _forecast_summary(forecast: list | None) -> list[dict]:
    if not forecast:
        return []
    out = []
    for day in forecast[:3]:
        out.append(
            {
                "datetime": day.get("datetime"),
                "condition": day.get("condition"),
                "temperature": day.get("temperature"),
                "templow": day.get("templow"),
                "precipitation": day.get("precipitation"),
            }
        )
    return out
