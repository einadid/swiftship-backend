"""SwiftShip — Courier & Logistics Management Platform (Backend)

Phitron Final Exam — Software Development Project (SDP)

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .database import Base, engine
from .routers import auth, parcels, services, users
from .seed import seed_data

Base.metadata.create_all(bind=engine)
seed_data()

app = FastAPI(
    title="SwiftShip Courier API",
    version="1.0.0",
    description=(
        "Backend API for the **SwiftShip Courier & Logistics Management Platform** — "
        "Phitron Final Exam SDP project. "
        "Features: JWT auth (bcrypt) with refresh tokens, admin/user roles, forgot password, "
        "parcel CRUD, search/filter/sort/pagination, public tracking, admin analytics."
    ),
)

# CORS configuration: allow frontend dev/production origins
cors_env = os.getenv("CORS_ORIGINS", "")
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if cors_env:
    for o in cors_env.split(","):
        o_clean = o.strip()
        if o_clean and o_clean not in allowed_origins:
            allowed_origins.append(o_clean)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if cors_env != "*" else ["*"],
    allow_origin_regex=r"^https?://.*$" if cors_env == "*" or not cors_env else None,
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
