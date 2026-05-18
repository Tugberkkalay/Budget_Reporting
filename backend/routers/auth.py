"""Auth router: login, logout, me, forgot/reset password."""
import os
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks
from pydantic import BaseModel, EmailStr
from database import db
from dependencies import get_current_user, _uid, _now
from auth_utils import hash_password, verify_password, create_access_token
from email_service import send_password_reset

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str


@router.post("/login")
async def login(body: LoginInput, response: Response, request: Request):
    email = body.email.lower().strip()
    ident = f"{request.client.host}:{email}" if request.client else email
    attempts = await db.login_attempts.find_one({"identifier": ident})
    if attempts and attempts.get("count", 0) >= 5:
        locked_until = attempts.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Çok fazla başarısız giriş. 15 dakika sonra tekrar deneyin.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"count": 1}, "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Email veya şifre hatalı")

    await db.login_attempts.delete_one({"identifier": ident})
    token = create_access_token(user["id"], user["email"], user.get("role", "viewer"))
    response.set_cookie(key="access_token", value=token, httponly=True, secure=False, samesite="lax", max_age=60*60*24*7, path="/")
    return {"id": user["id"], "email": user["email"], "name": user.get("name"), "role": user.get("role", "viewer"), "token": token}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordInput, background: BackgroundTasks):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"ok": True}
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.password_reset_tokens.insert_one({
        "id": _uid(), "token": token, "user_id": user["id"],
        "expires_at": expires_at, "used": False, "created_at": _now()
    })
    frontend = os.environ.get("FRONTEND_URL", "")
    link = f"{frontend}/reset-password?token={token}" if frontend else f"/reset-password?token={token}"
    background.add_task(send_password_reset, email, link)
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordInput):
    tok = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
    if not tok:
        raise HTTPException(status_code=400, detail="Geçersiz veya kullanılmış token")
    expires_at = tok["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token süresi dolmuş")
    await db.users.update_one({"id": tok["user_id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await db.password_reset_tokens.update_one({"id": tok["id"]}, {"$set": {"used": True}})
    return {"ok": True}
