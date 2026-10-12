from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from . import store
from .config import settings as env_settings
from .ha_client import HAClient
from .models import Plant
from .watering import as_utc, compute_fertilize, compute_watering

log = logging.getLogger("plants.notify")


def _where(plant: Plant) -> str:
    return f" ({plant.location})" if plant.location else ""


def _smtp_config(db: Session) -> dict:
    """Resolve SMTP settings from the DB, falling back to the environment."""
    def get(key: str, default):
        return store.get_value(db, key, default)

    try:
        port = int(get("smtp_port", env_settings.smtp_port))
    except (TypeError, ValueError):
        port = 587
    tls_raw = get("smtp_tls", env_settings.smtp_tls)
    if isinstance(tls_raw, bool):
        tls = tls_raw
    else:
        tls = str(tls_raw).strip().lower() in {"1", "true", "yes", "on"}
    user = (get("smtp_user", env_settings.smtp_user) or "").strip()
    return {
        "host": (get("smtp_host", env_settings.smtp_host) or "").strip(),
        "port": port,
        "user": user,
        "password": get("smtp_password", env_settings.smtp_password) or "",
        "from": (get("smtp_from", env_settings.smtp_from) or "").strip() or user,
        "tls": tls,
    }


async def dispatch(db: Session, title: str, body: str) -> dict:
    """Send one message through every configured channel."""
    results: dict = {"ha": [], "email": {"ok": False, "error": ""}}

    services = store.get_value(db, "notify_services", env_settings.notify_services) or []
    ha = HAClient(db)
    for service in services:
        ok = await ha.call_notify(service, body, title)
        results["ha"].append({"service": service, "ok": ok})

    recipients = store.get_value(db, "email_to", env_settings.email_to) or []
    if recipients:
        results["email"] = await asyncio.to_thread(
            _send_email, _smtp_config(db), title, body, recipients
        )
    else:
        results["email"] = {"ok": False, "error": "no email recipients configured"}

    return results


def build_watering_message(plants_due: list[Plant], env: dict, env_for=None) -> tuple[str, str]:
    """Build the reminder. ``env_for(plant)`` can supply a per-plant (room-aware)
    environment; it falls back to the shared ``env``."""
    title = "Plant watering reminder"
    if len(plants_due) == 1:
        title = f"Water: {plants_due[0].name}"

    lines = []
    for plant in plants_due:
        res = compute_watering(plant, env_for(plant) if env_for else env)
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


def _send_email(config: dict, subject: str, body: str, recipients: list[str]) -> dict:
    host = config.get("host") or ""
    if not host:
        return {"ok": False, "error": "SMTP host is not configured"}
    if not recipients:
        return {"ok": False, "error": "no email recipients configured"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.get("from") or config.get("user") or ""
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    port = config.get("port") or 587
    tls = bool(config.get("tls"))
    user = config.get("user") or ""
    try:
        # Implicit TLS on 465; STARTTLS on everything else (587, 25).
        if tls and port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            smtp = smtplib.SMTP(host, port, timeout=20)
        with smtp:
            if tls and port != 465:
                smtp.starttls()
            if user:
                smtp.login(user, config.get("password") or "")
            smtp.send_message(msg)
        return {"ok": True, "error": ""}
    except smtplib.SMTPAuthenticationError as exc:
        err = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        log.warning("SMTP authentication failed: %s", err)
        return {"ok": False, "error": f"authentication failed: {err}"}
    except Exception as exc:  # noqa: BLE001 - surface any SMTP/socket error to the UI
        log.warning("Email notification failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def send_reminders(db: Session, plants_due: list[Plant], env: dict, env_for=None) -> dict:
    title, body = build_watering_message(plants_due, env, env_for)
    return await dispatch(db, title, body)


async def send_sick_reminders(db: Session, plants: list[Plant]) -> dict:
    title, body = build_sick_message(plants)
    return await dispatch(db, title, body)


async def send_fertilize_reminders(db: Session, plants: list[Plant], months: list[int]) -> dict:
    title, body = build_fertilize_message(plants, months)
    return await dispatch(db, title, body)
