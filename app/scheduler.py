from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import environment, store
from .config import settings as env_settings
from .ha_client import HAClient
from .models import Plant, Reading, SessionLocal
from .notifications import send_fertilize_reminders, send_reminders, send_sick_reminders
from .watering import compute_fertilize, compute_watering

log = logging.getLogger("plants.scheduler")

scheduler = AsyncIOScheduler()


def _tz(db) -> ZoneInfo:
    name = store.get_value(db, "timezone", env_settings.timezone) or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


async def refresh_environment() -> dict:
    with SessionLocal() as db:
        env = await HAClient(db).get_weather()
        if env.get("available"):
            db.add(
                Reading(
                    outdoor_temp_c=env.get("outdoor_temp_c"),
                    indoor_temp_c=None,
                    condition=env.get("condition"),
                    rain_mm=env.get("rain_mm"),
                )
            )
            db.commit()
    return env


async def run_daily_check() -> None:
    with SessionLocal() as db:
        env, states, rooms = await environment.collect(db)
        plants = db.query(Plant).filter(Plant.active == 1).all()
        now = datetime.now(timezone.utc)

        def env_for(plant: Plant) -> dict:
            return environment.resolve(plant, env, states, rooms)

        due = [p for p in plants if compute_watering(p, env_for(p)).status in {"overdue", "due"}]
        if due:
            results = await send_reminders(db, due, env, env_for=env_for)
            log.info("Sent watering reminder for %d plant(s): %s", len(due), results)

        sick = [p for p in plants if p.is_sick]
        if sick:
            results = await send_sick_reminders(db, sick)
            log.info("Sent sick-plant check-up for %d plant(s): %s", len(sick), results)

        months = store.get_value(db, "fertilize_months", env_settings.fertilize_months) or []
        if now.month in set(months):
            fed = [
                p
                for p in plants
                if compute_fertilize(p, months, now).status in {"overdue", "due"}
            ]
            if fed:
                results = await send_fertilize_reminders(db, fed, months)
                log.info("Sent fertilize reminder for %d plant(s): %s", len(fed), results)

        if not due and not sick:
            log.info("No plants need water or a check-up today.")


def schedule_daily(hour: int, minute: int, tz: ZoneInfo) -> None:
    scheduler.add_job(
        run_daily_check,
        CronTrigger(hour=hour, minute=minute, timezone=tz),
        id="daily_check",
        replace_existing=True,
    )


def reschedule() -> None:
    with SessionLocal() as db:
        notify_time = store.get_value(db, "notify_time", env_settings.notify_time) or "08:00"
        tz = _tz(db)
    try:
        hour, minute = (int(x) for x in notify_time.split(":")[:2])
    except (ValueError, AttributeError):
        hour, minute = 8, 0
    schedule_daily(hour, minute, tz)
    log.info("Daily check scheduled for %02d:%02d %s", hour, minute, tz)


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reschedule()
    scheduler.add_job(
        refresh_environment,
        "interval",
        minutes=30,
        id="refresh_env",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
