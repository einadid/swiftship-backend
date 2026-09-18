"""Shared FastAPI dependencies: current user / current admin resolution."""
import jwt as pyjwt

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import security
from .database import get_db
from .models import User

bearer_scheme = HTTPBearer(auto_error=False)


def _credentials_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: Session = Depends(get_db),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(default=None),
) -> User:
    """Resolve the authenticated user from the Bearer token."""
    token = None
    if cred and cred.credentials:
        token = cred.credentials
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise _credentials_exception("Not authenticated")

    try:
        payload = security.decode_token(token, purpose="access")
    except pyjwt.ExpiredSignatureError:
        raise _credentials_exception("Token expired")
    except pyjwt.PyJWTError:
        raise _credentials_exception("Invalid token")

    token_type = payload.get("type") or payload.get("purpose")
    if token_type != "access":
        raise _credentials_exception("Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_exception("Invalid token")

    user = db.get(User, int(user_id))
    if user is None:
        raise _credentials_exception("User no longer exists")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked. Contact support.")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Route protection: only allow users with the admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
