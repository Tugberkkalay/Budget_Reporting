"""Users router (admin only) + audit logs."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from database import db
from dependencies import get_current_user, require_admin, write_audit, _uid, _now
from auth_utils import hash_password

router = APIRouter(tags=["users"])


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    new_password: Optional[str] = None


@router.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)


@router.post("/users")
async def create_user(body: RegisterInput, user: dict = Depends(require_admin)):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Bu email zaten kayıtlı")
    doc = {
        "id": _uid(), "email": email, "name": body.name, "role": body.role,
        "password_hash": hash_password(body.password), "active": True, "created_at": _now()
    }
    await db.users.insert_one(doc)
    await write_audit(user, "create", "user", doc["id"], {"email": email})
    doc.pop("password_hash", None); doc.pop("_id", None)
    return doc


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: dict = Depends(require_admin)):
    update = {}
    if body.name is not None: update["name"] = body.name
    if body.role is not None: update["role"] = body.role
    if body.active is not None: update["active"] = body.active
    if body.new_password: update["password_hash"] = hash_password(body.new_password)
    if not update:
        return {"ok": True}
    await db.users.update_one({"id": user_id}, {"$set": update})
    await write_audit(user, "update", "user", user_id, {k: v for k, v in update.items() if k != "password_hash"})
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
    await db.users.delete_one({"id": user_id})
    await write_audit(user, "delete", "user", user_id)
    return {"ok": True}


@router.get("/audit-logs")
async def list_audit(limit: int = 200, user: dict = Depends(require_admin)):
    return await db.audit_logs.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
