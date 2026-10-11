"""Resolve the environmental inputs for a plant, including per-room sensors."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .ha_client import HAClient
from .models import Plant, Room


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(name: str) -> str:
    return (name or "").strip().casefold()


async def collect(db: Session) -> tuple[dict, dict, dict]:
    """Return (global env, states by entity_id, rooms by normalized name)."""
    client = HAClient(db)
    env = await client.get_weather()
    states = {s.get("entity_id"): s for s in await client.get_all_states()}
    rooms = {_norm(r.name): r for r in db.query(Room).all()}
    return env, states, rooms


def resolve(plant: Plant, env: dict, states: dict, rooms: dict) -> dict:
    """Merge a plant's room sensors (temp + humidity) over the global env."""
    result = dict(env)
    if (plant.placement or "indoor").lower() != "indoor" or not plant.location:
        return result
    room = rooms.get(_norm(plant.location))
    if not room:
        return result
    if room.temp_entity and room.temp_entity in states:
        temp = _num(states[room.temp_entity].get("state"))
        if temp is not None:
            result["indoor_temp_c"] = temp
            result["available"] = True
    if room.humidity_entity and room.humidity_entity in states:
        humidity = _num(states[room.humidity_entity].get("state"))
        if humidity is not None:
            result["humidity"] = humidity
    return result
