"""Resolve the environmental inputs for a plant, including per-room sensors.

Rooms are Home Assistant areas; the sensors linked to each room come from the HA
registries (see :meth:`HAClient.get_rooms`). A plant stores the room it lives in
plus the temperature/humidity entities chosen for it in the editor.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .ha_client import HAClient
from .models import Plant


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_indoor(plant: Plant) -> bool:
    return (plant.placement or "indoor").lower() == "indoor"


def _single_sensor(room: dict | None, kind: str) -> str:
    sensors = (room or {}).get(f"{kind}_sensors") or []
    return sensors[0]["entity_id"] if len(sensors) == 1 else ""


async def collect(db: Session) -> tuple[dict, dict, dict]:
    """Return (global env, states by entity_id, rooms by area_id)."""
    client = HAClient(db)
    env = await client.get_weather()
    states = {s.get("entity_id"): s for s in await client.get_all_states()}
    rooms = {r["area_id"]: r for r in await client.get_rooms(states=states)}
    return env, states, rooms


def resolve(plant: Plant, env: dict, states: dict, rooms: dict) -> dict:
    """Merge a plant's room temp + humidity sensors over the global env."""
    result = dict(env)
    if not _is_indoor(plant):
        return result

    room = rooms.get(plant.room_id) if plant.room_id else None
    temp_entity = plant.temp_entity or _single_sensor(room, "temperature")
    humidity_entity = plant.humidity_entity or _single_sensor(room, "humidity")

    if temp_entity and temp_entity in states:
        temp = _num(states[temp_entity].get("state"))
        if temp is not None:
            result["indoor_temp_c"] = temp
            result["available"] = True
    if humidity_entity and humidity_entity in states:
        humidity = _num(states[humidity_entity].get("state"))
        if humidity is not None:
            result["humidity"] = humidity
    else:
        # Indoor plants shouldn't inherit the weather entity's humidity, which is
        # an outdoor reading. Only a room humidity sensor applies.
        result.pop("humidity", None)
    return result


def sensor_warning(plant: Plant, rooms: dict) -> bool:
    """True when an indoor plant has no usable temperature or humidity sensor."""
    if not _is_indoor(plant):
        return False
    room = rooms.get(plant.room_id) if plant.room_id else None
    has_temp = bool(plant.temp_entity) or bool((room or {}).get("temperature_sensors"))
    has_humidity = bool(plant.humidity_entity) or bool((room or {}).get("humidity_sensors"))
    return not (has_temp or has_humidity)
