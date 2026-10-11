from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import environment, store
from ..config import settings as env_settings
from ..ha_client import HAClient
from ..models import Plant, Setting, get_db
from ..notifications import send_reminders
from ..plantnet import PlantNetClient
from ..schemas import SettingsOut, SettingsUpdate
from ..scheduler import reschedule
from ..watering import compute_watering

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/weather")
async def get_weather(db: Session = Depends(get_db)):
    return await HAClient(db).get_weather()


@router.get("/ha/entities")
async def ha_entities(db: Session = Depends(get_db)):
    """List Home Assistant entities for the settings autocomplete."""
    states = await HAClient(db).get_all_states()
    out = []
    for state in states:
        entity_id = state.get("entity_id", "")
        if not entity_id:
            continue
        attrs = state.get("attributes", {})
        out.append(
            {
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or entity_id,
                "domain": entity_id.split(".")[0],
                "device_class": attrs.get("device_class"),
                "unit": attrs.get("unit_of_measurement"),
            }
        )
    return out


@router.get("/status")
async def status(db: Session = Depends(get_db)):
    env, states, rooms = await environment.collect(db)
    plants = db.query(Plant).filter(Plant.active == 1).all()
    due = [
        p
        for p in plants
        if compute_watering(p, environment.resolve(p, env, states, rooms)).status in {"overdue", "due"}
    ]
    configured = [
        store.get_value(db, "ha_weather_entity", env_settings.ha_weather_entity),
        store.get_value(db, "ha_outdoor_temp_entity", env_settings.ha_outdoor_temp_entity),
        store.get_value(db, "ha_indoor_temp_entity", env_settings.ha_indoor_temp_entity),
        store.get_value(db, "ha_rain_entity", env_settings.ha_rain_entity),
    ]
    return {
        "ha_configured": bool(env_settings.ha_token and env_settings.ha_url),
        "ha_reachable": bool(states),
        "ha_state_count": len(states),
        "entities_configured": any(configured) or bool(rooms),
        "plantnet_configured": bool(PlantNetClient(db).api_key),
        "plant_count": len(plants),
        "due_count": len(due),
        "environment": env,
    }


@router.get("/ha/notify-services")
async def ha_notify_services(db: Session = Depends(get_db)):
    """List the notify.* services available in Home Assistant (for the settings field)."""
    return await HAClient(db).get_notify_services()


@router.get("/ha/suggest")
async def ha_suggest(db: Session = Depends(get_db)):
    """Best-guess entity IDs for the settings fields, from the live HA state list."""
    states = await HAClient(db).get_all_states()

    def attr(state, key):
        return state.get("attributes", {}).get(key)

    weather = next((s["entity_id"] for s in states if s["entity_id"].startswith("weather.")), "")

    temps = [
        s for s in states
        if s["entity_id"].startswith("sensor.")
        and (attr(s, "device_class") == "temperature" or attr(s, "unit_of_measurement") in ("°C", "°F"))
    ]

    def pick(keywords):
        for s in temps:
            hay = (s["entity_id"] + " " + str(attr(s, "friendly_name") or "")).lower()
            if any(k in hay for k in keywords):
                return s["entity_id"]
        return ""

    outdoor = pick(["outdoor", "outside", "exterior", "externa", "exterieur", "street", "roof", "aseo"])
    indoor = pick(["indoor", "inside", "interior", "interna", "living", "sala", "salon", "bedroom", "bed ", "cuarto"])
    if not indoor:
        remaining = [s["entity_id"] for s in temps if s["entity_id"] != outdoor]
        if len(remaining) == 1:
            indoor = remaining[0]

    def is_rain(state):
        if not state["entity_id"].startswith("sensor."):
            return False
        dc = str(attr(state, "device_class") or "")
        return dc.startswith("precipitation") or attr(state, "unit_of_measurement") in ("mm", "in")

    rain = next((s["entity_id"] for s in states if is_rain(s)), "")
    return {
        "weather": weather,
        "outdoor_temp": outdoor,
        "indoor_temp": indoor,
        "rain": rain,
        "state_count": len(states),
    }


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return store.all_settings(db)


@router.put("/settings", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        store.set_value(db, key, value)
    if "notify_time" in data or "timezone" in data:
        reschedule()
    return store.all_settings(db)


@router.post("/notify/test")
async def test_notification(db: Session = Depends(get_db)):
    env = await HAClient(db).get_weather()
    plants = db.query(Plant).limit(3).all()
    if not plants:
        plants = [Plant(name="Test plant", base_interval_days=7)]
    return await send_reminders(db, plants, env)
