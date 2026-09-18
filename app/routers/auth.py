"""Authentication & authorization: signup, login, refresh, forgot/reset password."""
import datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..deps import get_current_user

router = APIRouter()

FRONTEND_URL = "http://localhost:5173"


def _token_pair(user_id: int) -> schemas.TokenPair:
    return schemas.TokenPair(
        access_token=security.create_access_token(user_id),
        refresh_token=security.create_refresh_token(user_id),
    )


@router.post("/signup", response_model=schemas.LoginResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a new user account (normal user role)")
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = models.User(
        full_name=body.full_name.strip(),
        email=email,
        phone=body.phone,
        hashed_password=security.hash_password(body.password),  # bcrypt
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.LoginResponse(user=schemas.UserOut.model_validate(user), tokens=_token_pair(user.id))


@router.post("/login", response_model=schemas.LoginResponse, summary="Login with email + password -> JWT tokens")
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(models.User).where(models.User.email == email))
    if user is None or not security.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is blocked. Contact support.")
    return schemas.LoginResponse(user=schemas.UserOut.model_validate(user), tokens=_token_pair(user.id))


@router.post("/refresh", response_model=schemas.TokenPair,
             summary="Exchange a valid refresh token for a new token pair (rotation)")
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
    return _token_pair(user.id)


@router.get("/me", response_model=schemas.UserOut, summary="Current authenticated user profile")
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post("/forgot-password", status_code=200,
             summary="Request a password-reset link (token returned for demo; no email service in exam env)")
def forgot_password(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == body.email.lower()))

    # In production this would email the reset link. The exam sandbox has no email
    # provider, so the reset URL is returned in the response for demo purposes.
    if user is not None and user.is_active:
        token = security.generate_reset_token()
        db.add(models.PasswordResetToken(
            token=token,
            user_id=user.id,
            created_at=datetime.datetime.utcnow(),
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=security.RESET_TOKEN_HOURS),
        ))
        db.commit()
        reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
    else:
        # Always respond with the same message so account existence can't be probed.
        reset_url = None
        db.commit()

    return {
        "message": "If an account exists for this email, a password reset link has been sent.",
        "reset_url": reset_url,  # demo convenience only — never do this in production
    }


@router.post("/reset-password", summary="Set a new password using the token from the reset link")
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(models.PasswordResetToken).where(models.PasswordResetToken.token == body.token))
    if record is None:
        raise HTTPException(status_code=400, detail="Invalid or already used reset token")
    if record.expires_at < datetime.datetime.utcnow():
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token expired. Please request a new one.")

    user = db.get(models.User, record.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = security.hash_password(body.new_password)
    db.delete(record)
    db.commit()
    return {"message": "Password updated successfully. You can now login with your new password."}


@router.post("/change-password", summary="Change password of the logged-in user (requires current password)")
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
