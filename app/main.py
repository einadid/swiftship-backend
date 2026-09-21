"""SwiftShip — Courier & Logistics Management Platform (Backend)

Phitron Final Exam — Software Development Project (SDP)

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .database import Base, engine
from .routers import auth, parcels, services, users
from .seed import seed_data

# Create tables at import time so that TestClient and simple imports work
# (lifespan will also ensure it on production startup)
try:
    Base.metadata.create_all(bind=engine)
    # Seed at import for test environment; lifespan will re-seed idempotently in production
    seed_data()
except Exception as e:
    print(f"[init] DB init warning (will retry on startup): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables and seed demo data
    try:
        Base.metadata.create_all(bind=engine)
        seed_data()
    except Exception as e:
        # Log but don't crash - DB might be locked during reload
        print(f"[lifespan] DB init warning: {e}")
    yield
    # Shutdown: dispose engine
    try:
        engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="SwiftShip Courier API",
    version="1.0.0",
    description=(
        "Backend API for the **SwiftShip Courier & Logistics Management Platform** — "
        "Phitron Final Exam SDP project. "
        "Features: JWT auth (bcrypt) with refresh tokens, admin/user roles, forgot password, "
        "parcel CRUD, search/filter/sort/pagination, public tracking, admin analytics."
    ),
    lifespan=lifespan,
)

# CORS configuration: allow frontend dev/production origins
# Env CORS_ORIGINS can be:
# - empty (default): allow localhost + regex for any http(s) origin, credentials True
# - "*" : allow all origins, credentials False (required for wildcard)
# - comma-separated list: e.g. "https://my-frontend.vercel.app,https://my-frontend.netlify.app"
cors_env = os.getenv("CORS_ORIGINS", "").strip()

default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

if cors_env == "*" or cors_env == "":
    # Permissive for exam/demo: allow all origins via regex, but don't allow credentials with "*"
    # Frontend uses Authorization header (not cookies), so credentials=False is fine
    if cors_env == "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Empty env: allow default origins + any https?://* via regex, with credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=default_origins,
            allow_origin_regex=r"^https?://.*$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
else:
    allowed = list(default_origins)
    for o in cors_env.split(","):
        o_clean = o.strip()
        if o_clean and o_clean not in allowed:
            allowed.append(o_clean)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(parcels.router, prefix="/api/parcels", tags=["Parcels"])
app.include_router(services.router, prefix="/api/services", tags=["Services"])
app.include_router(users.router, prefix="/api/users", tags=["Users (admin)"])


@app.get("/", include_in_schema=False)
def root():
    """Base URL opens the interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/api/health", tags=["Health"], summary="Health check")
def health():
    return {"status": "ok", "service": "SwiftShip Courier API", "version": "1.0.0"}
