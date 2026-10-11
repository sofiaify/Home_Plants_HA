from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from . import store
from .config import settings as env_settings
from .ha_client import HAClient
from .models import Plant
from .watering import as_utc, compute_fertilize, compute_watering

log = logging.getLogger("plants.notify")


def _where(plant: Plant) -> str:
    return f" ({plant.location})" if plant.location else ""


async def dispatch(db: Session, title: str, body: str) -> dict:
    """Send one message through every configured channel."""
    results: dict = {"ha": [], "email": False, "ntfy": False, "whatsapp": False}

    services = store.get_value(db, "notify_services", env_settings.notify_services) or []
    ha = HAClient(db)
    for service in services:
        ok = await ha.call_notify(service, body, title)
        results["ha"].append({"service": service, "ok": ok})

    results["ntfy"] = await _send_ntfy(db, title, body)
    results["whatsapp"] = await _send_whatsapp(db, body)

    recipients = store.get_value(db, "email_to", env_settings.email_to) or []
    if recipients:
        results["email"] = await asyncio.to_thread(_send_email, title, body, recipients)

    return results


async def _send_ntfy(db: Session, title: str, body: str) -> bool:
    topic = store.get_value(db, "ntfy_topic", env_settings.ntfy_topic) or ""
    if not topic:
        return False
    server = (store.get_value(db, "ntfy_server", env_settings.ntfy_server) or "https://ntfy.sh").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{server}/{topic}",
                content=body.encode(),
                headers={"Title": title, "Tags": "potted_plant"},
            )
        return resp.status_code < 400
    except httpx.HTTPError as exc:
        log.warning("ntfy notification failed: %s", exc)
        return False


async def _send_whatsapp(db: Session, body: str) -> bool:
    phone = store.get_value(db, "whatsapp_phone", env_settings.whatsapp_phone) or ""
    apikey = store.get_value(db, "whatsapp_apikey", env_settings.whatsapp_apikey) or ""
    if not phone or not apikey:
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.callmebot.com/whatsapp.php",
                params={"phone": phone, "text": body, "apikey": apikey},
            )
        return resp.status_code < 400
    except httpx.HTTPError as exc:
        log.warning("WhatsApp (CallMeBot) notification failed: %s", exc)
        return False


def build_watering_message(plants_due: list[Plant], env: dict) -> tuple[str, str]:
    title = "Plant watering reminder"
    if len(plants_due) == 1:
        title = f"Water: {plants_due[0].name}"

    lines = []
    for plant in plants_due:
        res = compute_watering(plant, env)
        if res.days_until_due is None:
            when = "never watered yet"
        elif res.days_until_due < 0:
            when = f"overdue by {abs(res.days_until_due):.0f} day(s)"
        else:
            when = "due today"
        lines.append(f"- {plant.name}{_where(plant)}: {when}")

    body = "Time to water these plants:\n\n" + "\n".join(lines) + "\n\nOpen the Plants app to mark them as watered."
    return title, body


def build_sick_message(plants: list[Plant]) -> tuple[str, str]:
    title = "Plant check-up" if len(plants) != 1 else f"Check on {plants[0].name}"
    now = datetime.now(timezone.utc)
    lines = []
    for plant in plants:
        since = as_utc(plant.sick_since)
        days = int((now - since).days) if since else 0
        note = f" — {plant.sick_note}" if plant.sick_note else ""
        lines.append(f"- {plant.name}{_where(plant)}: sick for {days} day(s){note}")
    body = (
        "These plants are marked as sick. Please check on them:\n\n"
        + "\n".join(lines)
        + "\n\nOpen the Plants app to add notes or mark them healthy."
    )
    return title, body


def build_fertilize_message(plants: list[Plant], months: list[int]) -> tuple[str, str]:
    title = "Fertilize reminder"
    now = datetime.now(timezone.utc)
    lines = []
    for plant in plants:
        res = compute_fertilize(plant, months, now)
        if res.fertilize_days_until is None or res.fertilize_days_until < 0:
            when = "overdue"
        elif res.fertilize_days_until < 1:
            when = "due today"
        else:
            when = f"due in {res.fertilize_days_until:.0f} day(s)"
        lines.append(f"- {plant.name}{_where(plant)}: {when}")
    body = (
        "It's the growing season — time to feed these plants:\n\n"
        + "\n".join(lines)
        + "\n\nOpen the Plants app to mark them as fed."
    )
    return title, body


def _send_email(subject: str, body: str, recipients: list[str]) -> bool:
    if not env_settings.smtp_host or not recipients:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env_settings.smtp_from or env_settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    try:
        with smtplib.SMTP(env_settings.smtp_host, env_settings.smtp_port, timeout=15) as smtp:
            if env_settings.smtp_tls:
                smtp.starttls()
            if env_settings.smtp_user:
                smtp.login(env_settings.smtp_user, env_settings.smtp_password)
            smtp.send_message(msg)
        return True
    except OSError as exc:
        log.warning("Email notification failed: %s", exc)
        return False


async def send_reminders(db: Session, plants_due: list[Plant], env: dict) -> dict:
    title, body = build_watering_message(plants_due, env)
    return await dispatch(db, title, body)


async def send_sick_reminders(db: Session, plants: list[Plant]) -> dict:
    title, body = build_sick_message(plants)
    return await dispatch(db, title, body)


async def send_fertilize_reminders(db: Session, plants: list[Plant], months: list[int]) -> dict:
    title, body = build_fertilize_message(plants, months)
    return await dispatch(db, title, body)
