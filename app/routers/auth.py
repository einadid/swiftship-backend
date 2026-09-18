"""Authentication & authorization: signup, login, refresh, forgot/reset password."""
import datetime
import os
import secrets

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..deps import get_current_user

router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _token_pair(user: models.User) -> schemas.TokenPair:
    return schemas.TokenPair(
        access_token=security.create_access_token(user.id, user.role),
        refresh_token=security.create_refresh_token(user.id, user.role),
        expires_in=security.ACCESS_TOKEN_MINUTES * 60,
    )


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


@router.post(
    "/signup",
    response_model=schemas.LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account (normal user role)",
)
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = models.User(
        full_name=body.full_name.strip(),
        email=email,
        phone=body.phone,
        hashed_password=security.hash_password(body.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.LoginResponse(user=schemas.UserOut.model_validate(user), tokens=_token_pair(user))


@router.post(
    "/login",
    response_model=schemas.LoginResponse,
    summary="Login with email + password -> JWT tokens",
)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(models.User).where(models.User.email == email))
    if user is None or not security.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is blocked. Contact support.")
    return schemas.LoginResponse(user=schemas.UserOut.model_validate(user), tokens=_token_pair(user))


@router.post(
    "/refresh",
    response_model=schemas.TokenPair,
    summary="Exchange a valid refresh token for a new token pair (rotation)",
)
def refresh(body: schemas.RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = security.decode_token(body.refresh_token, purpose="refresh")
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired. Please login again.")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token. Please login again.")

    user = db.get(models.User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return _token_pair(user)


@router.get(
    "/me",
    response_model=schemas.UserOut,
    summary="Current authenticated user profile",
)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post(
    "/forgot-password",
    status_code=200,
    summary="Request a password-reset link (returns demo reset URL in exam sandbox)",
)
def forgot_password(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == body.email.lower()))

    reset_url = None
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        expiry = utcnow() + datetime.timedelta(hours=security.RESET_TOKEN_HOURS)
        user.reset_token = token
        user.reset_token_expiry = expiry

        # Also store in PasswordResetToken table for compatibility
        db.add(models.PasswordResetToken(token=token, user_id=user.id, created_at=utcnow(), expires_at=expiry))
        db.commit()
        reset_url = f"{FRONTEND_URL}/reset-password?token={token}"

    return {
        "message": "If an account exists for that email, a reset link has been sent.",
        "reset_url": reset_url,
    }


@router.post(
    "/reset-password",
    summary="Set a new password using the token from the reset link",
)
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    now = utcnow()

    # Check User model directly first
    user = db.scalar(select(models.User).where(models.User.reset_token == body.token))
    if user and user.reset_token_expiry and user.reset_token_expiry >= now:
        user.hashed_password = security.hash_password(body.new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        # Clean up any PasswordResetToken records
        tokens = db.scalars(select(models.PasswordResetToken).where(models.PasswordResetToken.token == body.token)).all()
        for t in tokens:
            db.delete(t)
        db.commit()
        return {"message": "Password updated successfully. You can now login with your new password."}

    # Fallback to PasswordResetToken table
    record = db.scalar(select(models.PasswordResetToken).where(models.PasswordResetToken.token == body.token))
    if record is None:
        raise HTTPException(status_code=400, detail="Invalid or already used reset token")
    if record.expires_at < now:
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token expired. Please request a new one.")

    target_user = db.get(models.User, record.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.hashed_password = security.hash_password(body.new_password)
    target_user.reset_token = None
    target_user.reset_token_expiry = None
    db.delete(record)
    db.commit()
    return {"message": "Password updated successfully. You can now login with your new password."}


@router.post(
    "/change-password",
    summary="Change password of the logged-in user (requires current password)",
)
def change_password(
    body: schemas.ChangePasswordRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not security.verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = security.hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed successfully"}
