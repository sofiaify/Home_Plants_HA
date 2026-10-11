#!/usr/bin/env bash
set -e

# Home Assistant add-ons hand their configuration to the container as JSON.
if [ -f /data/options.json ]; then
  eval "$(python3 - <<'PY'
import json, shlex

try:
    opt = json.load(open("/data/options.json"))
except Exception:
    opt = {}

mapping = {
    "ha_weather_entity": "HA_WEATHER_ENTITY",
    "ha_outdoor_temp_entity": "HA_OUTDOOR_TEMP_ENTITY",
    "ha_indoor_temp_entity": "HA_INDOOR_TEMP_ENTITY",
    "ha_rain_entity": "HA_RAIN_ENTITY",
    "smtp_host": "SMTP_HOST",
    "smtp_user": "SMTP_USER",
    "smtp_password": "SMTP_PASSWORD",
    "smtp_from": "SMTP_FROM",
    "notify_time": "NOTIFY_TIME",
    "timezone": "TZ",
    "plantnet_api_key": "PLANTNET_API_KEY",
    "plantnet_project": "PLANTNET_PROJECT",
    "plantnet_lang": "PLANTNET_LANG",
}
print('export HA_URL=${HA_URL:-http://supervisor/core}')
print('export PLANTS_DATA_DIR=/data')
for key, env in mapping.items():
    value = opt.get(key)
    if value not in (None, ""):
        print(f"export {env}={shlex.quote(str(value))}")
for key, env in (
    ("notify_services", "NOTIFY_SERVICES"),
    ("email_to", "EMAIL_TO"),
    ("fertilize_months", "FERTILIZE_MONTHS"),
):
    value = opt.get(key)
    if value:
        print(f"export {env}={shlex.quote(','.join(str(v) for v in value))}")
PY
)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8099
