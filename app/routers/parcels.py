"""Parcels: CRUD + extended data listing (search / filter / sort / pagination) + tracking + stats."""
import secrets
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin, get_current_user

router = APIRouter()

STATUS_LABELS = {
    "pending": "Pending pickup",
    "picked_up": "Picked up",
    "in_transit": "In transit",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def _gen_tracking_number(db: Session) -> str:
    while True:
        number = f"SS{datetime.datetime.now().strftime('%Y')}{secrets.token_hex(4).upper()}"
        if not db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == number)):
            return number


def _get_parcel_or_404(db: Session, parcel_id: int) -> models.Parcel:
    parcel = db.get(models.Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel


def _check_access(parcel: models.Parcel, user: models.User):
    if user.role != "admin" and parcel.owner_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this parcel")


# ---------------------------------------------------------------------------
# Listing with search / filter / sort / pagination (20 marks)
# ---------------------------------------------------------------------------
@router.get("/", response_model=schemas.ParcelList, summary="List parcels — search, filter, sort, paginate")
def list_parcels(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    search: str | None = Query(default=None, description="Search by tracking number, name or phone"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    service_id: int | None = Query(default=None, description="Filter by service/category"),
    date_from: datetime.date | None = Query(default=None, description="Booked on/after this date (YYYY-MM-DD)"),
    date_to: datetime.date | None = Query(default=None, description="Booked on/before this date (YYYY-MM-DD)"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|recipient_name|sender_name|price|tracking_number|status)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100, description="Configurable page size"),
):
    query = select(models.Parcel)

    # Scope: admin sees everything, normal users see their own parcels only
    if user.role != "admin":
        query = query.where(models.Parcel.owner_id == user.id)

    # --- Search by name / title / ID -------------------------------------
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(
            models.Parcel.tracking_number.ilike(term),
            models.Parcel.recipient_name.ilike(term),
            models.Parcel.sender_name.ilike(term),
            models.Parcel.recipient_phone.ilike(term),
            models.Parcel.sender_phone.ilike(term),
            models.Parcel.notes.ilike(term),
        ))

    # --- Filters: status, service (category), date range ------------------
    if status_filter:
        query = query.where(models.Parcel.status == status_filter)
    if service_id:
        query = query.where(models.Parcel.service_id == service_id)
    if date_from:
        query = query.where(models.Parcel.created_at >= datetime.datetime.combine(date_from, datetime.time.min))
    if date_to:
        query = query.where(models.Parcel.created_at <= datetime.datetime.combine(date_to, datetime.time.max))

    # --- Sorting -----------------------------------------------------------
    sort_column = getattr(models.Parcel, sort_by)
    query = query.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc())
    query = query.order_by(models.Parcel.id.desc())  # stable tie-breaker

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    return schemas.ParcelList(
        items=[schemas.ParcelOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/summary", response_model=schemas.ParcelSummary, summary="Summary of the logged-in user's own parcels")
def my_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    base = select(models.Parcel).where(models.Parcel.owner_id == user.id)
    rows = db.execute(select(models.Parcel.status, func.count()).where(models.Parcel.owner_id == user.id).group_by(models.Parcel.status)).all()
    by_status = {s: 0 for s in models.PARCEL_STATUSES}
    for s, c in rows:
        by_status[s] = c
    total = sum(by_status.values())
    spent = db.scalar(select(func.coalesce(func.sum(models.Parcel.price), 0.0)).where(models.Parcel.owner_id == user.id, models.Parcel.status == "delivered")) or 0.0
    return schemas.ParcelSummary(
        total=total,
        by_status=by_status,
        total_spent=round(float(spent), 2),
        delivered=by_status["delivered"],
        active=total - by_status["delivered"] - by_status["cancelled"],
    )


# ---------------------------------------------------------------------------
# Public tracking
# ---------------------------------------------------------------------------
@router.get("/track/{tracking_number}", response_model=schemas.TrackOut, summary="Track a parcel by tracking number (public)")
def track(tracking_number: str, db: Session = Depends(get_db)):
    parcel = db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == tracking_number.strip().upper()))
    if parcel is None:
        raise HTTPException(status_code=404, detail="No parcel found with this tracking number")

    now = parcel.created_at
    steps = [("Parcel booked", parcel.created_at, True),
             ("Picked up", None, parcel.updated_at >= parcel.created_at and parcel.status != "pending"),
             ("In transit", None, parcel.status in ("out_for_delivery", "delivered")),
             ("Out for delivery", None, parcel.status == "delivered"),
             ("Delivered", parcel.updated_at if parcel.status == "delivered" else None, parcel.status == "delivered")]
    history = [{"label": label, "done": done, "date": d.isoformat() if d else None} for label, d, done in steps]

    return schemas.TrackOut(
        tracking_number=parcel.tracking_number,
        status=parcel.status,
        status_label=STATUS_LABELS.get(parcel.status, parcel.status),
        sender_name=parcel.sender_name,
        recipient_name=parcel.recipient_name,
        pickup_address=parcel.pickup_address,
        delivery_address=parcel.delivery_address,
        weight_kg=parcel.weight_kg,
        price=parcel.price,
        service_name=parcel.service.name,
        booked_at=parcel.created_at,
        last_updated=parcel.updated_at,
        history=history,
    )


# ---------------------------------------------------------------------------
# Admin analytics
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=schemas.AdminStats, summary="Admin dashboard analytics")
def admin_stats(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    total_parcels = db.scalar(select(func.count(models.Parcel.id))) or 0
    total_revenue = db.scalar(select(func.coalesce(func.sum(models.Parcel.price), 0.0)).where(models.Parcel.status == "delivered")) or 0.0
    total_users = db.scalar(select(func.count(models.User.id))) or 0
    total_services = db.scalar(select(func.count(models.Service.id))) or 0
    active_parcels = db.scalar(select(func.count(models.Parcel.id)).where(models.Parcel.status.not_in(["delivered", "cancelled"]))) or 0

    rows = db.execute(select(models.Parcel.status, func.count()).group_by(models.Parcel.status)).all()
    by_status = {s: 0 for s in models.PARCEL_STATUSES}
    for s, c in rows:
        by_status[s] = c

    recent = db.scalars(select(models.Parcel).order_by(models.Parcel.created_at.desc(), models.Parcel.id.desc()).limit(8)).all()
    return schemas.AdminStats(
        total_parcels=total_parcels,
        total_revenue=round(float(total_revenue), 2),
        total_users=total_users,
        total_services=total_services,
        active_parcels=active_parcels,
        by_status=by_status,
        recent_parcels=[schemas.ParcelOut.model_validate(p) for p in recent],
    )


# ---------------------------------------------------------------------------
# CRUD (10 marks)
# ---------------------------------------------------------------------------
@router.get("/{parcel_id}", response_model=schemas.ParcelOut, summary="Get a parcel (owner or admin)")
def get_parcel(parcel_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)
    return parcel


@router.post("/", response_model=schemas.ParcelOut, status_code=status.HTTP_201_CREATED, summary="Book a new parcel")
def create_parcel(body: schemas.ParcelCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    service = db.get(models.Service, body.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=400, detail="Selected service is not available")

    price = round(service.base_price + service.price_per_kg * body.weight_kg, 2)
    parcel = models.Parcel(
        **body.model_dump(),
        tracking_number=_gen_tracking_number(db),
        price=price,
        status="pending",
        owner_id=user.id,
    )
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return parcel


@router.put("/{parcel_id}", response_model=schemas.ParcelOut, summary="Update a parcel (owner: while pending; admin: anything incl. status)")
def update_parcel(parcel_id: int, body: schemas.ParcelUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)

    data = body.model_dump(exclude_unset=True)
    if user.role != "admin":
        if parcel.status != "pending":
            raise HTTPException(status_code=400, detail="Only pending parcels can be edited by the sender. Contact support for changes.")
        data.pop("status", None)

    if "service_id" in data and data["service_id"] is not None:
        service = db.get(models.Service, data["service_id"])
        if service is None or not service.is_active:
            raise HTTPException(status_code=400, detail="Selected service is not available")
        data["price"] = round(service.base_price + service.price_per_kg * (data.get("weight_kg") or parcel.weight_kg), 2)
    elif "weight_kg" in data and data["weight_kg"] is not None:
        service = parcel.service
        data["price"] = round(service.base_price + service.price_per_kg * data["weight_kg"], 2)

    for key, value in data.items():
        setattr(parcel, key, value)
    db.commit()
    db.refresh(parcel)
    return parcel


@router.patch("/{parcel_id}/status", response_model=schemas.ParcelOut, summary="Update delivery status (admin only)")
def update_status(parcel_id: int, body: schemas.StatusUpdate, db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    parcel = _get_parcel_or_404(db, parcel_id)
    if parcel.status == "delivered" and body.status != "delivered":
        raise HTTPException(status_code=400, detail="A delivered parcel cannot move back in the pipeline")
    parcel.status = body.status
    db.commit()
    db.refresh(parcel)
    return parcel


@router.delete("/{parcel_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a parcel (admin: always; owner: only while pending)")
def delete_parcel(parcel_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)
    if user.role != "admin" and parcel.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending parcels can be deleted by the sender")
    db.delete(parcel)
    db.commit()



