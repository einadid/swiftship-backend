"""User management (admin only): list/search/paginate, block/unblock, password reset."""
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..deps import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("", response_model=schemas.UserPage, include_in_schema=False)
@router.get("/", response_model=schemas.UserPage, summary="List users with search + pagination (admin only)")
def list_users(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
    search: str | None = Query(default=None, description="Search by name, email or phone"),
    role: str | None = Query(default=None, pattern="^(user|admin)$"),
    is_active: bool | None = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(created_at|full_name|email)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = select(models.User)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                models.User.full_name.ilike(term),
                models.User.email.ilike(term),
                models.User.phone.ilike(term),
            )
        )
    if role:
        query = query.where(models.User.role == role)
    if is_active is not None:
        query = query.where(models.User.is_active.is_(is_active))

    sort_column = getattr(models.User, sort_by)
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    query = query.order_by(models.User.id.desc())

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    total_pages = max(1, math.ceil(total / page_size))

    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return schemas.UserPage(
        items=[schemas.UserOut.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{user_id}", response_model=schemas.UserOut, summary="Get a single user (admin only)")
def get_user(user_id: int, db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}/active", response_model=schemas.UserOut, summary="Block / unblock a user (admin only)")
def set_active(
    user_id: int,
    body: schemas.UserActiveUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot block or unblock your own account")
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = body.is_active
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", summary="Force-reset a user's password (admin only)")
def reset_password(
    user_id: int,
    body: schemas.AdminSetPassword,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = security.hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    return {"message": f"Password for {user.email} has been reset"}
