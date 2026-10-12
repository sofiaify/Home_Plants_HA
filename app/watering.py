from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import Plant

WET_CONDITIONS = {"rainy", "pouring", "lightning-rainy", "snowy", "snowy-rainy", "hail"}
DRY_CONDITIONS = {"sunny", "windy", "windy-variant"}


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class WateringResult:
    effective_interval_days: float
    next_due: datetime | None
    days_until_due: float | None
    status: str
    adjustment_factor: float
    adjustment_reason: str
    # temp+humidity only (excludes weather/rain): >1 helps keep humidity, <1 dries
    hydration_factor: float = 1.0


def compute_watering(plant: Plant, env: dict | None, now: datetime | None = None) -> WateringResult:
    now = as_utc(now) or datetime.now(timezone.utc)
    env = env or {}

    indoor = (plant.placement or "indoor").lower() == "indoor"
    # Indoor plants only use an indoor temperature (room sensor or the configured
    # indoor entity). Never fall back to the weather entity's temperature, which
    # is an outdoor reading.
    if indoor:
        temp = env.get("indoor_temp_c")
    else:
        temp = env.get("outdoor_temp_c")
        if temp is None:
            temp = env.get("temperature")

    factor = 1.0
    hydration = 1.0  # temperature × humidity contribution only
    reasons: list[tuple[float, str]] = []

    if temp is not None:
        try:
            temp = float(temp)
            temp_factor = 1.0 - (temp - 21.0) * 0.03
            temp_factor = _clamp(temp_factor, 0.6, 1.5)
            factor *= temp_factor
            hydration *= temp_factor
            if temp_factor < 0.98:
                reasons.append((abs(1 - temp_factor), f"warm ({temp:.0f}°C) speeds drying"))
            elif temp_factor > 1.02:
                reasons.append((abs(1 - temp_factor), f"cool ({temp:.0f}°C) slows drying"))
        except (TypeError, ValueError):
            pass

    humidity = env.get("humidity")
    if humidity is not None:
        try:
            humidity = float(humidity)
            if humidity >= 70:
                factor *= 1.1
                hydration *= 1.1
                reasons.append((0.1, f"high humidity ({humidity:.0f}%)"))
            elif humidity <= 35:
                factor *= 0.92
                hydration *= 0.92
                reasons.append((0.08, f"low humidity ({humidity:.0f}%)"))
        except (TypeError, ValueError):
            pass

    condition = (env.get("condition") or "").lower()
    if not indoor and condition:
        if condition in WET_CONDITIONS:
            factor *= 1.25
            reasons.append((0.25, f"{condition.replace('-', ' ')} outdoors"))
        elif condition in DRY_CONDITIONS:
            factor *= 0.9
            reasons.append((0.1, f"{condition} outdoors"))

    rain = env.get("rain_mm")
    if not indoor and rain is not None:
        try:
            rain = float(rain)
            if rain >= 2:
                factor *= 1.3
                reasons.append((0.3, f"recent rain ({rain:.0f} mm)"))
        except (TypeError, ValueError):
            pass

    factor = _clamp(factor, 0.5, 1.6)
    effective = _clamp(plant.base_interval_days * factor, 1.0, plant.base_interval_days * 1.6)

    last = as_utc(plant.last_watered)
    next_due = last + timedelta(days=effective) if last else None

    if next_due is None:
        status = "overdue"
        days_until = None
    else:
        days_until = (next_due - now).total_seconds() / 86400
        if days_until < 0:
            status = "overdue"
        elif days_until < 1:
            status = "due"
        elif days_until <= 2:
            status = "soon"
        else:
            status = "ok"

    if not plant.active:
        status = "inactive"

    reason = max(reasons, key=lambda r: r[0])[1] if reasons else "season baseline"

    override = (plant.status_override or "").lower()
    if plant.active and override in {"ok", "due", "overdue", "soon"}:
        status = override
        reason = "manual override"

    return WateringResult(
        effective_interval_days=round(effective, 1),
        next_due=next_due,
        days_until_due=round(days_until, 2) if days_until is not None else None,
        status=status,
        adjustment_factor=round(factor, 3),
        adjustment_reason=reason,
        hydration_factor=round(hydration, 3),
    )


@dataclass
class FertilizeResult:
    next_fertilize_due: datetime | None
    fertilize_days_until: float | None
    status: str  # off | offseason | overdue | due | ok
    in_season: bool


def compute_fertilize(
    plant: Plant, months: list[int] | None, now: datetime | None = None
) -> FertilizeResult:
    """Fertilizing is only scheduled during the configured growing months."""
    now = as_utc(now) or datetime.now(timezone.utc)

    if not plant.fertilize_interval_days or plant.fertilize_interval_days <= 0:
        return FertilizeResult(None, None, "off", False)

    in_season = now.month in set(months or [])
    if not in_season:
        return FertilizeResult(None, None, "offseason", False)

    baseline = as_utc(plant.last_fertilized) or as_utc(plant.created_at) or now
    next_due = baseline + timedelta(days=plant.fertilize_interval_days)
    days = (next_due - now).total_seconds() / 86400
    if days < 0:
        status = "overdue"
    elif days < 3:
        status = "due"
    else:
        status = "ok"
    return FertilizeResult(next_due, round(days, 2), status, True)
