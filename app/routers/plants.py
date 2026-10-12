from __future__ import annotations

import shutil
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import PHOTO_DIR
from ..config import settings as env_settings
from .. import environment, store
from ..ha_client import HAClient
from ..models import Plant, PlantPhoto, WateringEvent, get_db
from ..schemas import (
    PlantCreate,
    PlantOut,
    PlantPhotoOut,
    PlantUpdate,
    SickRequest,
    WaterRequest,
)
from ..watering import as_utc, compute_fertilize, compute_watering

router = APIRouter(prefix="/api/plants", tags=["plants"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def _months(db: Session) -> list[int]:
    return store.get_value(db, "fertilize_months", env_settings.fertilize_months) or []


def _to_out(
    plant: Plant, env: dict, months: list[int] | None = None, rooms: dict | None = None
) -> PlantOut:
    res = compute_watering(plant, env)
    fert = compute_fertilize(plant, months or [])
    return PlantOut(
        id=plant.id,
        name=plant.name,
        species=plant.species,
        location=plant.location,
        placement=plant.placement,
        room_id=plant.room_id,
        room_name=plant.room_name,
        temp_entity=plant.temp_entity,
        humidity_entity=plant.humidity_entity,
        sensor_warning=environment.sensor_warning(plant, rooms or {}),
        base_interval_days=plant.base_interval_days,
        fertilize_interval_days=plant.fertilize_interval_days,
        is_sick=bool(plant.is_sick),
        sick_note=plant.sick_note,
        notes=plant.notes,
        active=bool(plant.active),
        photo=plant.photo,
        photos=[PlantPhotoOut(id=ph.id, filename=ph.filename) for ph in plant.photos],
        last_watered=as_utc(plant.last_watered),
        next_due=res.next_due,
        days_until_due=res.days_until_due,
        status=res.status,
        effective_interval_days=res.effective_interval_days,
        adjustment_factor=res.adjustment_factor,
        adjustment_reason=res.adjustment_reason,
        hydration_factor=res.hydration_factor,
        sick_since=as_utc(plant.sick_since),
        next_fertilize_due=fert.next_fertilize_due,
        fertilize_days_until=fert.fertilize_days_until,
        fertilize_status=fert.status,
        fertilize_in_season=fert.in_season,
    )


async def _env_result(db: Session, plant: Plant) -> PlantOut:
    env, states, rooms = await environment.collect(db)
    return _to_out(plant, environment.resolve(plant, env, states, rooms), _months(db), rooms)


@router.get("", response_model=list[PlantOut])
async def list_plants(db: Session = Depends(get_db)):
    months = _months(db)
    plants = db.query(Plant).order_by(Plant.name).all()
    env, states, rooms = await environment.collect(db)
    return [_to_out(p, environment.resolve(p, env, states, rooms), months, rooms) for p in plants]


@router.post("", response_model=PlantOut, status_code=201)
async def create_plant(payload: PlantCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    last = data.pop("last_watered", None) or datetime.now(timezone.utc)
    if "is_sick" in data:
        data["is_sick"] = 1 if data["is_sick"] else 0
    plant = Plant(**data)
    plant.last_watered = as_utc(last)
    if plant.is_sick:
        plant.sick_since = datetime.now(timezone.utc)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    db.add(WateringEvent(plant_id=plant.id, watered_at=plant.last_watered, method="manual"))
    db.commit()
    return await _env_result(db, plant)


@router.get("/{plant_id}", response_model=PlantOut)
async def get_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    return await _env_result(db, plant)


@router.patch("/{plant_id}", response_model=PlantOut)
async def update_plant(plant_id: int, payload: PlantUpdate, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    data = payload.model_dump(exclude_unset=True)
    if "active" in data:
        data["active"] = 1 if data["active"] else 0
    if "is_sick" in data:
        sick = 1 if data["is_sick"] else 0
        if sick and not plant.is_sick:
            plant.sick_since = datetime.now(timezone.utc)
        if not sick:
            plant.sick_since = None
        data["is_sick"] = sick
    for key, value in data.items():
        setattr(plant, key, value)
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/sick", response_model=PlantOut)
async def mark_sick(plant_id: int, payload: SickRequest, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    if not plant.is_sick:
        plant.sick_since = datetime.now(timezone.utc)
    plant.is_sick = 1
    if payload.note:
        plant.sick_note = payload.note
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/healthy", response_model=PlantOut)
async def mark_healthy(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    plant.is_sick = 0
    plant.sick_since = None
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/fertilize", response_model=PlantOut)
async def fertilize_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    plant.last_fertilized = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.delete("/{plant_id}", status_code=204)
async def delete_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    db.delete(plant)
    db.commit()


@router.post("/{plant_id}/water", response_model=PlantOut)
async def water_plant(plant_id: int, payload: WaterRequest, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    when = as_utc(payload.at) or datetime.now(timezone.utc)
    plant.last_watered = when
    db.add(WateringEvent(plant_id=plant.id, watered_at=when, method="manual", note=payload.note))
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/water/undo", response_model=PlantOut)
async def undo_water(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    events = (
        db.query(WateringEvent)
        .filter(WateringEvent.plant_id == plant_id)
        .order_by(WateringEvent.watered_at.desc(), WateringEvent.id.desc())
        .all()
    )
    if not events:
        raise HTTPException(400, "Nothing to undo")
    db.delete(events[0])
    db.flush()
    previous = events[1] if len(events) > 1 else None
    plant.last_watered = as_utc(previous.watered_at) if previous else None
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.get("/{plant_id}/history")
async def plant_history(plant_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    return [
        {"id": e.id, "watered_at": as_utc(e.watered_at), "method": e.method, "note": e.note}
        for e in plant.events
    ]


@router.post("/{plant_id}/photo", response_model=PlantOut)
async def upload_photo(plant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    suffix = IMAGE_SUFFIX.get(file.content_type)
    if not suffix:
        raise HTTPException(400, "Unsupported image type")

    if plant.photo:
        stale = PHOTO_DIR / plant.photo
        # Only remove the old cover if it isn't one of the gallery photos.
        gallery = {ph.filename for ph in plant.photos}
        if plant.photo not in gallery and stale.exists():
            stale.unlink()
    filename = f"plant-{plant.id}{suffix}"
    with open(PHOTO_DIR / filename, "wb") as out:
        shutil.copyfileobj(file.file, out)
    plant.photo = filename
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/photos", response_model=PlantOut)
async def add_photo(plant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    suffix = IMAGE_SUFFIX.get(file.content_type)
    if not suffix:
        raise HTTPException(400, "Unsupported image type")
    filename = f"plant-{plant.id}-{uuid4().hex[:10]}{suffix}"
    with open(PHOTO_DIR / filename, "wb") as out:
        shutil.copyfileobj(file.file, out)
    db.add(PlantPhoto(plant_id=plant.id, filename=filename))
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.delete("/{plant_id}/photos/{photo_id}", response_model=PlantOut)
async def delete_photo(plant_id: int, photo_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    photo = db.get(PlantPhoto, photo_id)
    if not photo or photo.plant_id != plant_id:
        raise HTTPException(404, "Photo not found")
    path = PHOTO_DIR / photo.filename
    db.delete(photo)
    db.commit()
    if path.exists():
        path.unlink()
    db.refresh(plant)
    return await _env_result(db, plant)


@router.post("/{plant_id}/photos/{photo_id}/cover", response_model=PlantOut)
async def set_cover(plant_id: int, photo_id: int, db: Session = Depends(get_db)):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    photo = db.get(PlantPhoto, photo_id)
    if not photo or photo.plant_id != plant_id:
        raise HTTPException(404, "Photo not found")
    source = PHOTO_DIR / photo.filename
    if not source.exists():
        raise HTTPException(404, "Photo file missing")
    suffix = source.suffix
    if plant.photo:
        stale = PHOTO_DIR / plant.photo
        gallery = {ph.filename for ph in plant.photos}
        if plant.photo not in gallery and stale.exists():
            stale.unlink()
    cover = f"plant-{plant.id}{suffix}"
    shutil.copyfile(source, PHOTO_DIR / cover)
    plant.photo = cover
    db.commit()
    db.refresh(plant)
    return await _env_result(db, plant)
