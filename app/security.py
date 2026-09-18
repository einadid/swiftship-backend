"""Security helpers: bcrypt password hashing + JWT creation/validation (PyJWT)."""
import datetime
import os
import secrets
import uuid

import bcrypt
import jwt

SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "swiftship-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
RESET_TOKEN_HOURS = int(os.getenv("RESET_TOKEN_HOURS", "1"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _make_token(data: dict, expires: datetime.timedelta, purpose: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        **data,
        "type": purpose,
        "purpose": purpose,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str = "user") -> str:
    return _make_token(
        {"sub": str(user_id), "role": role},
        datetime.timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "access",
    )


def create_refresh_token(user_id: int, role: str = "user") -> str:
    return _make_token(
        {"sub": str(user_id), "role": role},
        datetime.timedelta(days=REFRESH_TOKEN_DAYS),
        "refresh",
    )


def decode_token(token: str, purpose: str = "access") -> dict:
    """Decode + validate a JWT. Raises jwt.PyJWTError subclasses on any problem."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    token_type = payload.get("type") or payload.get("purpose")
    if purpose and token_type != purpose:
        raise jwt.InvalidTokenError(f"Invalid token type: expected {purpose}, got {token_type}")
    return payload


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)
