from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..config import PHOTO_DIR
from ..models import Plant, get_db
from ..plantnet import PlantNetClient, PlantNetError

router = APIRouter(prefix="/api", tags=["identify"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}


@router.post("/identify")
async def identify_upload(
    file: UploadFile = File(...),
    organ: str = Query("auto"),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "Pl@ntNet accepts JPEG or PNG images only.")
    image = await file.read()
    try:
        return await PlantNetClient(db).identify(image, file.filename or "photo.jpg", organ=organ)
    except PlantNetError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/plants/{plant_id}/identify")
async def identify_plant(
    plant_id: int,
    organ: str = Query("auto"),
    db: Session = Depends(get_db),
):
    plant = db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    if not plant.photo:
        raise HTTPException(400, "This plant has no photo to identify.")
    path = PHOTO_DIR / plant.photo
    if not path.exists():
        raise HTTPException(400, "The stored photo could not be found.")
    try:
        return await PlantNetClient(db).identify(path.read_bytes(), plant.photo, organ=organ)
    except PlantNetError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/identify/missing")
async def identify_missing(
    overwrite: bool = Query(False, description="Also re-identify plants that already have a species"),
    organ: str = Query("auto"),
    db: Session = Depends(get_db),
):
    query = db.query(Plant).filter(Plant.photo.isnot(None))
    if not overwrite:
        query = query.filter((Plant.species.is_(None)) | (Plant.species == ""))
    plants = query.all()

    client = PlantNetClient(db)
    results = []
    updated = 0
    remaining = None
    for plant in plants:
        path = PHOTO_DIR / plant.photo
        entry = {"id": plant.id, "name": plant.name, "species": None, "score": None, "error": None}
        if not path.exists():
            entry["error"] = "photo missing"
            results.append(entry)
            continue
        try:
            out = await client.identify(path.read_bytes(), plant.photo, organ=organ, nb_results=3)
            remaining = out.get("remaining_requests", remaining)
            candidates = out.get("candidates") or []
            if candidates:
                top = candidates[0]
                plant.species = top["scientific_name"]
                entry["species"] = top["scientific_name"]
                entry["score"] = top["score"]
                updated += 1
        except PlantNetError as exc:
            entry["error"] = str(exc)
        results.append(entry)

    db.commit()
    return {"updated": updated, "remaining_requests": remaining, "results": results}
