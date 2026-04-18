from pathlib import Path
import os
import sys

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import config_router
from service_controller import service_router
from system_stats import system_stats_router
from user import user_router

def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_runtime_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
RUNTIME_DIR = get_runtime_dir()
DOTENV_FILE = APP_DIR / ".env"

if load_dotenv is not None:
    load_dotenv(dotenv_path=DOTENV_FILE, override=False)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

STATIC_DIR = RUNTIME_DIR / "static"
STATIC_INDEX_FILE = STATIC_DIR / "index.html"



app = FastAPI(
    title="MasterDnsWeb API",
    description="",
    version="1.0.0"
)
_cors_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$" if not _cors_env else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(user_router)
app.include_router(config_router)
app.include_router(service_router)
app.include_router(system_stats_router)


def frontend_bundle_exists() -> bool:
    return STATIC_INDEX_FILE.exists()


def resolve_frontend_path(relative_path: str) -> Path:
    requested_path = (STATIC_DIR / relative_path.lstrip("/")).resolve()

    if requested_path != STATIC_DIR.resolve() and STATIC_DIR.resolve() not in requested_path.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return requested_path


def serve_frontend(relative_path: str = ""):
    if not frontend_bundle_exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend bundle not found")

    requested_path = resolve_frontend_path(relative_path)
    if requested_path.is_file():
        return FileResponse(requested_path)

    return FileResponse(STATIC_INDEX_FILE)


@app.get("/")
def root():
    if frontend_bundle_exists():
        return FileResponse(STATIC_INDEX_FILE)

    return {"status": "running", "message": "FastAPI server is running"}


@app.get("/api/health")
def health():
    return {"status": "running", "message": "FastAPI server is running"}

@app.get("/info")
def info():
    return {
        "name": "MasterDnsWeb API",
        "version": "1.0.0",
        "frontend_bundle": frontend_bundle_exists(),
    }


@app.get("/api/info")
def api_info():
    return info()


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return serve_frontend(full_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
