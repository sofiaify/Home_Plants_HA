from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str] = mapped_column(String(120), default="")
    placement: Mapped[str] = mapped_column(String(16), default="indoor")  # indoor | outdoor
    # Room (Home Assistant area) the plant lives in, plus the sensors chosen for it.
    room_id: Mapped[str] = mapped_column(String(120), default="")
    room_name: Mapped[str] = mapped_column(String(120), default="")
    temp_entity: Mapped[str] = mapped_column(String(120), default="")
    humidity_entity: Mapped[str] = mapped_column(String(120), default="")
    photo: Mapped[str | None] = mapped_column(String(255))
    base_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    last_watered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sick: Mapped[int] = mapped_column(Integer, default=0)
    sick_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sick_note: Mapped[str] = mapped_column(Text, default="")
    fertilize_interval_days: Mapped[int] = mapped_column(Integer, default=30)
    last_fertilized: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_override: Mapped[str] = mapped_column(String(16), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    events: Mapped[list["WateringEvent"]] = relationship(
        back_populates="plant", cascade="all, delete-orphan", order_by="WateringEvent.watered_at.desc()"
    )


class WateringEvent(Base):
    __tablename__ = "watering_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    watered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    method: Mapped[str] = mapped_column(String(32), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")

    plant: Mapped[Plant] = relationship(back_populates="events")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Reading(Base):
    """Cached environmental readings pulled from Home Assistant."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    outdoor_temp_c: Mapped[float | None] = mapped_column(Float)
    indoor_temp_c: Mapped[float | None] = mapped_column(Float)
    condition: Mapped[str | None] = mapped_column(String(80))
    rain_mm: Mapped[float | None] = mapped_column(Float)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate()


# Columns added after the first release, applied to existing SQLite databases.
_ADDED_COLUMNS = {
    "is_sick": "INTEGER NOT NULL DEFAULT 0",
    "sick_since": "DATETIME",
    "sick_note": "TEXT NOT NULL DEFAULT ''",
    "fertilize_interval_days": "INTEGER NOT NULL DEFAULT 30",
    "last_fertilized": "DATETIME",
    "status_override": "TEXT NOT NULL DEFAULT ''",
    "room_id": "TEXT NOT NULL DEFAULT ''",
    "room_name": "TEXT NOT NULL DEFAULT ''",
    "temp_entity": "TEXT NOT NULL DEFAULT ''",
    "humidity_entity": "TEXT NOT NULL DEFAULT ''",
}


def _migrate() -> None:
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(plants)")}
        for column, ddl in _ADDED_COLUMNS.items():
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE plants ADD COLUMN {column} {ddl}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
