"""Delivery services: public listing + admin CRUD."""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin, get_current_user

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


@router.get("", response_model=list[schemas.ServiceOut], include_in_schema=False)
@router.get(
    "/",
    response_model=list[schemas.ServiceOut],
    summary="List delivery services (public: active only; ?all=true: admin only)",
)
def list_services(
    all: bool = False,
    db: Session = Depends(get_db),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(default=None),
):
    query = select(models.Service).order_by(models.Service.name)
    if all:
        # Require admin for ?all=true
        user = get_current_user(db=db, cred=cred, authorization=authorization)
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin privileges required")
    else:
        query = query.where(models.Service.is_active.is_(True))

    return db.scalars(query).all()


@router.get("/{service_id}", response_model=schemas.ServiceOut, summary="Get a single service")
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.post(
    "",
    response_model=schemas.ServiceOut,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/",
    response_model=schemas.ServiceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a service (admin only)",
)
def create_service(
    body: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    if db.scalar(select(models.Service).where(models.Service.name == body.name.strip())):
        raise HTTPException(status_code=400, detail="A service with this name already exists")
    service = models.Service(**body.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.put("/{service_id}", response_model=schemas.ServiceOut, summary="Update a service (admin only)")
def update_service(
    service_id: int,
    body: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    service = db.get(models.Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name_val = data["name"].strip()
        clash = db.scalar(select(models.Service).where(models.Service.name == name_val, models.Service.id != service_id))
        if clash:
            raise HTTPException(status_code=400, detail="A service with this name already exists")
        data["name"] = name_val

    for key, value in data.items():
        setattr(service, key, value)

    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a service (admin only; unused only)")
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    service = db.get(models.Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    if db.scalar(select(models.Parcel).where(models.Parcel.service_id == service_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Service is used by existing parcels — deactivate it instead",
        )

    db.delete(service)
    db.commit()
