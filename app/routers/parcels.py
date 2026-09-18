"""Parcels: listing (search / filter / sort / pagination), CRUD, tracking, and admin stats."""
import datetime
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin, get_current_user

router = APIRouter()

SORTABLE = {"created_at", "tracking_number", "sender_name", "recipient_name", "price", "status"}

STATUS_LABELS = {
    "pending": "Pending pickup",
    "picked_up": "Picked up",
    "in_transit": "In transit",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def next_tracking_number(db: Session) -> str:
    year = datetime.datetime.now(datetime.timezone.utc).strftime("%Y")
    max_id = db.scalar(select(func.max(models.Parcel.id))) or 0
    seq = max_id + 1
    while True:
        num = f"SS{year}{seq:04d}"
        if not db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == num)):
            return num
        seq += 1


def _get_parcel_or_404(db: Session, parcel_id: int) -> models.Parcel:
    parcel = db.query(models.Parcel).options(
        joinedload(models.Parcel.service),
        joinedload(models.Parcel.owner),
    ).filter(models.Parcel.id == parcel_id).first()
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel


def _check_access(parcel: models.Parcel, user: models.User):
    if user.role != "admin" and parcel.owner_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this parcel")


# ---------------------------------------------------------------------------
# 1. Static & Special Routes (MUST be declared before dynamic /{parcel_id})
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=schemas.ParcelSummary, summary="Summary of the logged-in user's own parcels")
def my_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.execute(
        select(models.Parcel.status, func.count(models.Parcel.id))
        .where(models.Parcel.owner_id == user.id)
        .group_by(models.Parcel.status)
    ).all()

    by_status = {s: 0 for s in models.PARCEL_STATUSES}
    for s, c in rows:
        by_status[s] = c

    total = sum(by_status.values())
    delivered = by_status.get("delivered", 0)
    cancelled = by_status.get("cancelled", 0)
    active = total - delivered - cancelled

    spent = db.scalar(
        select(func.coalesce(func.sum(models.Parcel.price), 0.0))
        .where(models.Parcel.owner_id == user.id, models.Parcel.status == "delivered")
    ) or 0.0

    return schemas.ParcelSummary(
        total=total,
        active=active,
        delivered=delivered,
        cancelled=cancelled,
        total_spent=round(float(spent), 2),
        by_status=by_status,
    )


@router.get("/stats", response_model=schemas.AdminStats, summary="Admin dashboard analytics")
def admin_stats(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    total_parcels = db.scalar(select(func.count(models.Parcel.id))) or 0
    total_revenue = db.scalar(
        select(func.coalesce(func.sum(models.Parcel.price), 0.0))
        .where(models.Parcel.status == "delivered")
    ) or 0.0
    total_users = db.scalar(select(func.count(models.User.id))) or 0
    total_services = db.scalar(select(func.count(models.Service.id))) or 0
    active_parcels = db.scalar(
        select(func.count(models.Parcel.id))
        .where(models.Parcel.status.not_in(["delivered", "cancelled"]))
    ) or 0

    rows = db.execute(select(models.Parcel.status, func.count(models.Parcel.id)).group_by(models.Parcel.status)).all()
    by_status = {s: 0 for s in models.PARCEL_STATUSES}
    for s, c in rows:
        by_status[s] = c

    recent = db.scalars(
        select(models.Parcel)
        .options(joinedload(models.Parcel.service), joinedload(models.Parcel.owner))
        .order_by(models.Parcel.created_at.desc(), models.Parcel.id.desc())
        .limit(5)
    ).all()

    return schemas.AdminStats(
        total_parcels=total_parcels,
        active_parcels=active_parcels,
        total_revenue=round(float(total_revenue), 2),
        total_users=total_users,
        total_services=total_services,
        by_status=by_status,
        recent_parcels=[schemas.ParcelOut.model_validate(p) for p in recent],
    )


@router.get("/track/{tracking_number}", response_model=schemas.TrackOut, summary="Track a parcel by tracking number (public)")
def track(tracking_number: str, db: Session = Depends(get_db)):
    clean_tracking = tracking_number.strip().upper()
    parcel = db.query(models.Parcel).options(
        joinedload(models.Parcel.service)
    ).filter(
        func.upper(models.Parcel.tracking_number) == clean_tracking
    ).first()

    if parcel is None:
        raise HTTPException(status_code=404, detail="No parcel found with that tracking number")

    timeline_statuses = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered"]
    index = timeline_statuses.index(parcel.status) if parcel.status in timeline_statuses else -1
    steps = ["Booked", "Picked up", "In transit", "Out for delivery", "Delivered"]
    history = [{"label": s, "done": index >= i} for i, s in enumerate(steps)]

    return schemas.TrackOut(
        tracking_number=parcel.tracking_number,
        status=parcel.status,
        status_label=STATUS_LABELS.get(parcel.status, parcel.status.replace("_", " ").capitalize()),
        sender_name=parcel.sender_name,
        recipient_name=parcel.recipient_name,
        pickup_address=parcel.pickup_address,
        delivery_address=parcel.delivery_address,
        weight_kg=parcel.weight_kg,
        price=parcel.price,
        service_name=parcel.service.name if parcel.service else "",
        booked_at=parcel.created_at,
        last_updated=parcel.updated_at,
        history=history,
    )


# ---------------------------------------------------------------------------
# 2. List & Create (parcels/ and parcels)
# ---------------------------------------------------------------------------

@router.get("", response_model=schemas.ParcelList, include_in_schema=False)
@router.get("/", response_model=schemas.ParcelList, summary="List parcels — search, filter, sort, paginate")
def list_parcels(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    search: str | None = Query(default=None, description="Search tracking, sender, recipient, address, phone"),
    status: str | None = Query(default=None, description="Filter by status"),
    service_id: int | None = Query(default=None, description="Filter by service ID"),
    date_from: datetime.date | None = Query(default=None, description="Booked on/after this date (YYYY-MM-DD)"),
    date_to: datetime.date | None = Query(default=None, description="Booked on/before this date (YYYY-MM-DD)"),
    sort_by: str = Query(default="created_at", description="Sort field"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page"),
):
    query = select(models.Parcel).options(
        joinedload(models.Parcel.service),
        joinedload(models.Parcel.owner),
    )

    # User isolation: admin sees all, normal user sees own only
    if user.role != "admin":
        query = query.where(models.Parcel.owner_id == user.id)

    # Search
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                models.Parcel.tracking_number.ilike(term),
                models.Parcel.sender_name.ilike(term),
                models.Parcel.recipient_name.ilike(term),
                models.Parcel.sender_phone.ilike(term),
                models.Parcel.recipient_phone.ilike(term),
                models.Parcel.pickup_address.ilike(term),
                models.Parcel.delivery_address.ilike(term),
                models.Parcel.notes.ilike(term),
            )
        )

    # Filters
    if status:
        query = query.where(models.Parcel.status == status)
    if service_id:
        query = query.where(models.Parcel.service_id == service_id)
    if date_from:
        query = query.where(func.date(models.Parcel.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(models.Parcel.created_at) <= date_to)

    # Sorting with whitelist
    active_sort = sort_by if sort_by in SORTABLE else "created_at"
    sort_col = getattr(models.Parcel, active_sort)
    query = query.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())
    query = query.order_by(models.Parcel.id.desc())

    # Count total matching
    count_stmt = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_stmt) or 0

    page = max(1, page)
    page_size = min(100, max(1, page_size))
    total_pages = max(1, math.ceil(total / page_size))

    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    return schemas.ParcelList(
        items=[schemas.ParcelOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=schemas.ParcelOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=schemas.ParcelOut, status_code=status.HTTP_201_CREATED, summary="Book a new parcel")
def create_parcel(payload: schemas.ParcelCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    service = db.get(models.Service, payload.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=422, detail="Selected delivery service is not available")

    calculated_price = round(service.base_price + service.price_per_kg * payload.weight_kg, 2)
    tracking_num = next_tracking_number(db)

    parcel = models.Parcel(
        **payload.model_dump(),
        tracking_number=tracking_num,
        price=calculated_price,
        status="pending",
        owner_id=user.id,
    )
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return parcel


# ---------------------------------------------------------------------------
# 3. Dynamic /{parcel_id} Routes (At the end to avoid matching static paths)
# ---------------------------------------------------------------------------

@router.get("/{parcel_id}", response_model=schemas.ParcelOut, summary="Get parcel detail (owner or admin)")
def get_parcel(parcel_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)
    return parcel


@router.put("/{parcel_id}", response_model=schemas.ParcelOut, summary="Update parcel (pending for user; any for admin)")
def update_parcel(parcel_id: int, body: schemas.ParcelUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)

    data = body.model_dump(exclude_unset=True)
    if user.role != "admin":
        if parcel.status != "pending":
            raise HTTPException(status_code=400, detail="Only pending parcels can be edited")
        data.pop("status", None)

    # Price recalculation if service or weight changed
    if "service_id" in data and data["service_id"] is not None:
        service = db.get(models.Service, data["service_id"])
        if service is None or not service.is_active:
            raise HTTPException(status_code=422, detail="Selected delivery service is not available")
        weight = data.get("weight_kg", parcel.weight_kg)
        data["price"] = round(service.base_price + service.price_per_kg * weight, 2)
    elif "weight_kg" in data and data["weight_kg"] is not None:
        service = parcel.service
        data["price"] = round(service.base_price + service.price_per_kg * data["weight_kg"], 2)

    for key, value in data.items():
        setattr(parcel, key, value)

    parcel.updated_at = utcnow()
    db.commit()
    db.refresh(parcel)
    return parcel


@router.patch("/{parcel_id}/status", response_model=schemas.ParcelOut, summary="Update parcel status (admin only)")
def change_status(parcel_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    parcel = _get_parcel_or_404(db, parcel_id)
    if parcel.status == "delivered" and payload.status != "delivered":
        raise HTTPException(status_code=400, detail="A delivered parcel cannot move back in the pipeline")

    parcel.status = payload.status
    parcel.updated_at = utcnow()
    db.commit()
    db.refresh(parcel)
    return parcel


@router.delete("/{parcel_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete parcel (pending for user; any for admin)")
def delete_parcel(parcel_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    parcel = _get_parcel_or_404(db, parcel_id)
    _check_access(parcel, user)

    if user.role != "admin" and parcel.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending parcels can be deleted")

    db.delete(parcel)
    db.commit()
