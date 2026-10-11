from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlantBase(BaseModel):
    name: str = Field(..., max_length=120)
    species: str | None = Field(default=None, max_length=160)
    location: str = ""
    placement: str = "indoor"
    base_interval_days: int = Field(default=7, ge=1, le=400)
    fertilize_interval_days: int = Field(default=30, ge=0, le=400)
    is_sick: bool = False
    sick_note: str = ""
    status_override: str = ""
    notes: str = ""
    active: bool = True


class PlantCreate(PlantBase):
    last_watered: datetime | None = None


class PlantUpdate(BaseModel):
    name: str | None = None
    species: str | None = None
    location: str | None = None
    placement: str | None = None
    base_interval_days: int | None = Field(default=None, ge=1, le=400)
    fertilize_interval_days: int | None = Field(default=None, ge=0, le=400)
    is_sick: bool | None = None
    sick_note: str | None = None
    status_override: str | None = None
    last_watered: datetime | None = None
    notes: str | None = None
    active: bool | None = None


class RoomBase(BaseModel):
    name: str = Field(..., max_length=120)
    temp_entity: str = ""
    humidity_entity: str = ""


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: str | None = None
    temp_entity: str | None = None
    humidity_entity: str | None = None


class RoomOut(RoomBase):
    id: int


class PlantOut(PlantBase):
    id: int
    photo: str | None = None
    last_watered: datetime | None = None
    next_due: datetime | None = None
    effective_interval_days: float | None = None
    days_until_due: float | None = None
    status: str = "unknown"
    adjustment_factor: float = 1.0
    adjustment_reason: str = ""
    sick_since: datetime | None = None
    next_fertilize_due: datetime | None = None
    fertilize_days_until: float | None = None
    fertilize_status: str = "off"
    fertilize_in_season: bool = False


class WaterRequest(BaseModel):
    at: datetime | None = None
    note: str = ""


class SickRequest(BaseModel):
    note: str = ""


class SettingsOut(BaseModel):
    notify_time: str
    notify_services: list[str]
    email_to: list[str]
    ha_weather_entity: str
    ha_outdoor_temp_entity: str
    ha_indoor_temp_entity: str
    ha_rain_entity: str
    timezone: str
    plantnet_api_key: str
    plantnet_project: str
    plantnet_lang: str
    fertilize_months: list[int]
    ntfy_topic: str
    ntfy_server: str
    whatsapp_phone: str
    whatsapp_apikey: str


class SettingsUpdate(BaseModel):
    notify_time: str | None = None
    notify_services: list[str] | None = None
    email_to: list[str] | None = None
    ha_weather_entity: str | None = None
    ha_outdoor_temp_entity: str | None = None
    ha_indoor_temp_entity: str | None = None
    ha_rain_entity: str | None = None
    timezone: str | None = None
    plantnet_api_key: str | None = None
    plantnet_project: str | None = None
    plantnet_lang: str | None = None
    fertilize_months: list[int] | None = None
    ntfy_topic: str | None = None
    ntfy_server: str | None = None
    whatsapp_phone: str | None = None
    whatsapp_apikey: str | None = None


class IdentificationCandidate(BaseModel):
    score: float
    scientific_name: str
    common_names: list[str] = []
    family: str | None = None
    genus: str | None = None


class IdentificationResult(BaseModel):
    best_match: str | None = None
    predicted_organ: str | None = None
    remaining_requests: int | None = None
    candidates: list[IdentificationCandidate] = []
