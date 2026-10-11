from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .bootstrap import ensure_seeded, prepare_data_dir
from .config import PHOTO_DIR, settings
from .models import SessionLocal, init_db
from .routers import identify, plants, system
from .scheduler import start as start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs full request URLs at INFO, which would expose the Pl@ntNet API key.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_data_dir()
    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)
    start_scheduler()
    yield


app = FastAPI(title="Home Plants", version="1.0.2", lifespan=lifespan)


@app.middleware("http")
async def strip_ingress_prefix(request, call_next):
    """Home Assistant ingress serves the app under /api/hassio_ingress/<token>/.

    Strip that prefix so the regular routes match regardless of how the proxy
    forwards the path.
    """
    path = request.scope.get("path", "")
    marker = "/api/hassio_ingress/"
    if path.startswith(marker):
        remainder = path[len(marker):].partition("/")[2]
        request.scope["path"] = "/" + remainder
        request.scope["raw_path"] = request.scope["path"].encode()
    return await call_next(request)


@app.middleware("http")
async def no_store(request, call_next):
    """Never let the browser cache assets — a stale app.js breaks the UI after updates."""
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store, max-age=0")
    return response

app.include_router(plants.router)
app.include_router(identify.router)
app.include_router(system.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=PHOTO_DIR), name="photos")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
