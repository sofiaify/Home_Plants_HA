"""First-run seeding.

The bundled ``seed_data/photos`` folder holds the original plant photos. On the
very first start (empty database) these are copied into the writable photo
directory and a plant row is created for each, with a sensible default watering
interval. Later starts are a no-op.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from .config import BASE_DIR, DB_PATH, PHOTO_DIR
from .models import Plant

log = logging.getLogger("plants.bootstrap")

SEED_DIR = BASE_DIR / "seed_data" / "photos"
SEED_DB = BASE_DIR / "seed_data" / "plants.db"

# (bundled photo, display name, species, default days, placement)
SEED_PLANTS = [
    ("peace-lily.jpg", "Peace Lily", "Spathiphyllum wallisii", 7, "indoor"),
    ("lipstick-plant.jpg", "Lipstick Plant", "Aeschynanthus radicans", 10, "indoor"),
    ("white-heather.jpg", "White Heather", "Calluna vulgaris", 7, "outdoor"),
    ("golden-pothos.jpg", "Golden Pothos", "Epipremnum aureum", 8, "indoor"),
    ("white-heather-2.jpg", "White Heather (2nd angle)", "Calluna vulgaris", 7, "outdoor"),
    ("lavender.jpg", "Lavender", "Lavandula angustifolia", 14, "outdoor"),
    ("pink-heather.jpg", "Pink Heather", "Calluna vulgaris", 7, "outdoor"),
    ("dusty-miller.jpg", "Dusty Miller", "Jacobaea maritima", 10, "outdoor"),
    ("ornamental-shrub.jpg", "Ornamental Shrub", None, 7, "outdoor"),
    ("coleus.jpg", "Coleus", "Coleus scutellarioides", 6, "indoor"),
    ("nerve-plant.jpg", "Nerve Plant", "Fittonia albivenis", 5, "indoor"),
    ("alocasia.jpg", "Alocasia", "Alocasia amazonica", 7, "indoor"),
]


def prepare_data_dir() -> None:
    """Restore a bundled database (and its photos) on first run, if provided.

    ``deploy.sh`` can bundle your existing ``data/`` so the device starts with
    exactly the plants you already set up. Runs before the DB is opened.
    """
    if DB_PATH.exists():
        return
    if not SEED_DB.exists():
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SEED_DB, DB_PATH)
    log.info("Restored existing database from bundled data.")

    if SEED_DIR.exists():
        for photo in SEED_DIR.iterdir():
            if photo.is_file():
                shutil.copy2(photo, PHOTO_DIR / photo.name)


def ensure_seeded(db: Session) -> None:
    if db.query(Plant).count() > 0:
        return
    if not SEED_DIR.exists():
        log.info("No seed data found, starting empty.")
        return

    seeded = 0
    for photo, name, species, interval, placement in SEED_PLANTS:
        source = SEED_DIR / photo
        if not source.exists():
            continue
        target = PHOTO_DIR / photo
        if not target.exists():
            shutil.copy2(source, target)
        db.add(
            Plant(
                name=name,
                species=species,
                location="",
                placement=placement,
                photo=photo,
                base_interval_days=interval,
                notes="",
            )
        )
        seeded += 1
    db.commit()
    log.info("Seeded %d plants from bundled photos.", seeded)
