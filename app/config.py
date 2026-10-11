import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PLANTS_DATA_DIR", BASE_DIR / "data"))
PHOTO_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "plants.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime configuration. Values may be overridden by rows in the settings table."""

    def __init__(self) -> None:
        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        # When running as a Home Assistant add-on the Supervisor proxies the HA API.
        default_url = "http://supervisor/core" if supervisor_token else "http://homeassistant.local:8123"
        self.ha_url = os.environ.get("HA_URL", default_url).rstrip("/")
        self.ha_token = os.environ.get("HA_TOKEN", "") or (supervisor_token or "")

        self.ha_weather_entity = os.environ.get("HA_WEATHER_ENTITY", "")
        self.ha_outdoor_temp_entity = os.environ.get("HA_OUTDOOR_TEMP_ENTITY", "")
        self.ha_indoor_temp_entity = os.environ.get("HA_INDOOR_TEMP_ENTITY", "")
        self.ha_rain_entity = os.environ.get("HA_RAIN_ENTITY", "")

        # Comma separated list of notify services, e.g. "notify.mobile_app_sofia,notify.telegram"
        self.notify_services = [
            s.strip() for s in os.environ.get("NOTIFY_SERVICES", "").split(",") if s.strip()
        ]

        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.smtp_from = os.environ.get("SMTP_FROM", self.smtp_user)
        self.email_to = [s.strip() for s in os.environ.get("EMAIL_TO", "").split(",") if s.strip()]
        self.smtp_tls = _bool(os.environ.get("SMTP_TLS"), True)

        self.notify_time = os.environ.get("NOTIFY_TIME", "08:00")
        self.timezone = os.environ.get("TZ", "UTC")
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "8099"))

        # Pl@ntNet identification (https://my.plantnet.org)
        self.plantnet_api_key = os.environ.get("PLANTNET_API_KEY", "")
        self.plantnet_project = os.environ.get("PLANTNET_PROJECT", "all")
        self.plantnet_lang = os.environ.get("PLANTNET_LANG", "en")
        self.plantnet_base = os.environ.get("PLANTNET_BASE", "https://my-api.plantnet.org")

        # Months during which fertilizing reminders are active (northern spring/summer).
        self.fertilize_months = [
            int(m) for m in os.environ.get("FERTILIZE_MONTHS", "3,4,5,6,7,8").split(",") if m.strip().isdigit()
        ]


settings = Settings()
