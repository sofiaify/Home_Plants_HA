from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .config import settings as env_settings
from .models import Setting

# Keys that can be persisted in the DB and override the environment defaults.
OVERRIDABLE = {
    "notify_time",
    "notify_services",
    "email_to",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "smtp_from",
    "smtp_tls",
    "ha_weather_entity",
    "ha_outdoor_temp_entity",
    "ha_indoor_temp_entity",
    "ha_rain_entity",
    "timezone",
    "plantnet_api_key",
    "plantnet_project",
    "plantnet_lang",
    "fertilize_months",
}

_LIST_KEYS = {"notify_services", "email_to", "fertilize_months"}


def get_value(db: Session, key: str, default=None):
    row = db.get(Setting, key)
    if row is not None:
        raw = row.value
        if key in _LIST_KEYS:
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return [s.strip() for s in raw.split(",") if s.strip()]
        return raw
    # No UI override: prefer the environment value when one is set, else the
    # caller-provided default. (Empty strings / empty lists are valid env values.)
    env_value = getattr(env_settings, key, None)
    if env_value is not None:
        return env_value
    return default


def set_value(db: Session, key: str, value) -> None:
    if key not in OVERRIDABLE:
        raise KeyError(key)
    if isinstance(value, list):
        stored = json.dumps(value)
    else:
        stored = "" if value is None else str(value)
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=stored))
    else:
        row.value = stored
    db.commit()


def all_settings(db: Session) -> dict:
    return {key: get_value(db, key) for key in OVERRIDABLE}
