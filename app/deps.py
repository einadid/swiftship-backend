"""Shared FastAPI dependencies: current user / current admin resolution."""
import jwt as pyjwt

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import security
from .database import get_db
from .models import User


def _credentials_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    """Resolve the authenticated user from the `Authorization: Bearer <token>` header.

    Validates the JWT, checks expiry, and confirms the account still exists
    and is active.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _credentials_exception("Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = security.decode_token(token, purpose="access")
    except pyjwt.ExpiredSignatureError:
        raise _credentials_exception("Token expired")
    except pyjwt.PyJWTError:
        raise _credentials_exception("Invalid token")

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None:
        raise _credentials_exception("User no longer exists")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked. Contact support.")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Route protection: only allow users with the admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
