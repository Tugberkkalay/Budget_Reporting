"""EY Finans Platform — FastAPI backend."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from auth_utils import hash_password, verify_password, create_access_token, decode_token
from email_service import send_email, send_password_reset, send_payment_reminder
from seed_loader import seed_all, ensure_indexes
from ai_service import ocr_invoice, chat_with_assistant
from fx_service import update_fx_in_db

import aiofiles
from fastapi import UploadFile, File, Form
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ============================================================
# Setup
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="EY Finans Platform API")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Common utilities
# ============================================================
def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_current_user(request: Request) -> dict:
    """JWT'den kullanıcıyı çek (cookie veya Authorization header)."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekli")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Geçersiz token tipi")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yetkiniz yok (admin gerekli)")
    return user


async def write_audit(db, user: dict, action: str, resource: str, resource_id: Optional[str] = None, meta: Optional[dict] = None):
    try:
        await db.audit_logs.insert_one({
            "id": _uid(),
            "user_id": user.get("id"),
            "user_email": user.get("email"),
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "meta": meta or {},
            "ts": _now(),
        })
    except Exception as e:
        logger.warning("audit yazılamadı: %s", e)


# ============================================================
# AUTH MODULE
# ============================================================
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "viewer"


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str


@api.post("/auth/login")
async def login(body: LoginInput, response: Response, request: Request):
    email = body.email.lower().strip()
    ident = f"{request.client.host}:{email}" if request.client else email
    # Brute force check
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
    return {
        "id": user["id"], "email": user["email"], "name": user.get("name"),
        "role": user.get("role", "viewer"), "token": token
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordInput, background: BackgroundTasks):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        # Bilgi sızdırma — her zaman aynı cevap
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


@api.post("/auth/reset-password")
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


# ============================================================
# USERS MODULE (admin)
# ============================================================
@api.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users


@api.post("/users")
async def create_user(body: RegisterInput, user: dict = Depends(require_admin)):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Bu email zaten kayıtlı")
    doc = {
        "id": _uid(), "email": email, "name": body.name, "role": body.role,
        "password_hash": hash_password(body.password), "active": True, "created_at": _now()
    }
    await db.users.insert_one(doc)
    await write_audit(db, user, "create", "user", doc["id"], {"email": email})
    doc.pop("password_hash", None); doc.pop("_id", None)
    return doc


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    new_password: Optional[str] = None


@api.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: dict = Depends(require_admin)):
    update = {}
    if body.name is not None: update["name"] = body.name
    if body.role is not None: update["role"] = body.role
    if body.active is not None: update["active"] = body.active
    if body.new_password: update["password_hash"] = hash_password(body.new_password)
    if not update:
        return {"ok": True}
    await db.users.update_one({"id": user_id}, {"$set": update})
    await write_audit(db, user, "update", "user", user_id, {k: v for k, v in update.items() if k != "password_hash"})
    return {"ok": True}


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
    await db.users.delete_one({"id": user_id})
    await write_audit(db, user, "delete", "user", user_id)
    return {"ok": True}


# ============================================================
# MASTER DATA — Generic CRUD for parametric collections
# ============================================================
MASTER_COLLECTIONS = {
    "companies": ["name", "tax_no", "notes"],
    "armators": ["name", "notes"],
    "managers": ["name", "notes"],
    "ships": ["name", "manager", "armator", "imo", "flag", "notes"],
    "people": ["name", "notes"],
    "countries": ["name", "code"],
    "banks": ["name", "type", "currency", "iban", "balance", "company", "notes"],
    "expense_types": ["code", "name", "notes"],
    "accounting_codes": ["code", "name", "notes"],
    "vendors": ["name", "country", "tax_no", "iban", "contact", "phone", "email", "notes"],
    "currencies": ["code", "name", "rate_to_tl"],
    "payment_statuses": ["name", "color", "order"],
    "payment_methods": ["name", "notes"],
}


class MasterItem(BaseModel):
    model_config = ConfigDict(extra="allow")


@api.get("/master/{collection}")
async def list_master(collection: str, user: dict = Depends(get_current_user)):
    if collection not in MASTER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen koleksiyon")
    items = await db[collection].find({}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    return items


@api.post("/master/{collection}")
async def create_master(collection: str, body: MasterItem, user: dict = Depends(get_current_user)):
    if collection not in MASTER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen koleksiyon")
    doc = body.model_dump()
    doc["id"] = _uid()
    doc["active"] = doc.get("active", True)
    doc["created_at"] = _now()
    await db[collection].insert_one(doc)
    await write_audit(db, user, "create", collection, doc["id"])
    doc.pop("_id", None)
    return doc


@api.put("/master/{collection}/{item_id}")
async def update_master(collection: str, item_id: str, body: MasterItem, user: dict = Depends(get_current_user)):
    if collection not in MASTER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen koleksiyon")
    update = body.model_dump(exclude_unset=True)
    update.pop("id", None); update.pop("_id", None); update.pop("created_at", None)
    if not update:
        return {"ok": True}
    update["updated_at"] = _now()
    await db[collection].update_one({"id": item_id}, {"$set": update})
    await write_audit(db, user, "update", collection, item_id)
    return {"ok": True}


@api.delete("/master/{collection}/{item_id}")
async def delete_master(collection: str, item_id: str, user: dict = Depends(get_current_user)):
    if collection not in MASTER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen koleksiyon")
    await db[collection].delete_one({"id": item_id})
    await write_audit(db, user, "delete", collection, item_id)
    return {"ok": True}


# ============================================================
# PAYABLES (Borçlar) / RECEIVABLES (Alacaklar) — kind ile ayrılıyor
# ============================================================
class PayableInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    order_date: Optional[str] = None
    due_date: Optional[str] = None
    expense_code: Optional[str] = None
    expense_type: Optional[str] = None
    vendor: Optional[str] = None
    country: Optional[str] = None
    person_company: Optional[str] = None
    ship: Optional[str] = None
    armator: Optional[str] = None
    description: Optional[str] = None
    original_amount: Optional[float] = 0
    currency: Optional[str] = "USD"
    usd_amount: Optional[float] = 0
    status: Optional[str] = "ONAY BEKLİYOR"
    kind: Optional[str] = "PAYABLE"  # PAYABLE / RECEIVABLE


@api.get("/payables")
async def list_payables(
    kind: str = "PAYABLE",
    status: Optional[str] = None,
    ship: Optional[str] = None,
    vendor: Optional[str] = None,
    year: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(get_current_user),
):
    q: dict = {"kind": kind}
    if status: q["status"] = status
    if ship: q["ship"] = ship
    if vendor: q["vendor"] = vendor
    if year: q["year"] = year
    if search:
        q["$or"] = [
            {"description": {"$regex": search, "$options": "i"}},
            {"vendor": {"$regex": search, "$options": "i"}},
            {"ship": {"$regex": search, "$options": "i"}},
        ]
    items = await db.payables.find(q, {"_id": 0}).sort("due_date", -1).to_list(limit)
    return items


@api.post("/payables")
async def create_payable(body: PayableInput, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = _uid()
    if doc.get("due_date"):
        try:
            d = datetime.fromisoformat(doc["due_date"])
            doc["year"] = d.year
            doc["month"] = d.month
        except Exception:
            pass
    doc["created_at"] = _now()
    doc["created_by"] = user["email"]
    await db.payables.insert_one(doc)
    await write_audit(db, user, "create", "payable", doc["id"])
    doc.pop("_id", None)
    return doc


@api.get("/payables/{pid}")
async def get_payable(pid: str, user: dict = Depends(get_current_user)):
    item = await db.payables.find_one({"id": pid}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Bulunamadı")
    # bağlı ödemeler
    payments = await db.payments.find({"payable_id": pid}, {"_id": 0}).to_list(100)
    item["payments"] = payments
    return item


@api.put("/payables/{pid}")
async def update_payable(pid: str, body: PayableInput, user: dict = Depends(get_current_user)):
    update = body.model_dump(exclude_unset=True)
    update.pop("id", None)
    update["updated_at"] = _now()
    if update.get("due_date"):
        try:
            d = datetime.fromisoformat(update["due_date"])
            update["year"] = d.year
            update["month"] = d.month
        except Exception:
            pass
    await db.payables.update_one({"id": pid}, {"$set": update})
    await write_audit(db, user, "update", "payable", pid)
    return {"ok": True}


@api.delete("/payables/{pid}")
async def delete_payable(pid: str, user: dict = Depends(get_current_user)):
    await db.payables.delete_one({"id": pid})
    await write_audit(db, user, "delete", "payable", pid)
    return {"ok": True}


# ============================================================
# PAYMENTS (Ödeme / Tahsilat)
# ============================================================
class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Optional[str] = "TEDİYE"  # TEDİYE / TAHSİL
    date: Optional[str] = None
    payable_id: Optional[str] = None
    ship: Optional[str] = None
    vendor: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None
    paying_company: Optional[str] = None
    payment_method: Optional[str] = None  # banka/kasa adı
    amount: Optional[float] = 0
    currency: Optional[str] = "USD"
    fx_rate: Optional[float] = 1
    usd_amount: Optional[float] = 0
    approved: Optional[bool] = False


@api.get("/payments")
async def list_payments(
    type: Optional[str] = None,
    bank: Optional[str] = None,
    ship: Optional[str] = None,
    company: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 1000,
    user: dict = Depends(get_current_user),
):
    q: dict = {}
    if type: q["type"] = type
    if bank: q["payment_method"] = bank
    if ship: q["ship"] = ship
    if company: q["paying_company"] = company
    if search:
        q["$or"] = [
            {"description": {"$regex": search, "$options": "i"}},
            {"vendor": {"$regex": search, "$options": "i"}},
        ]
    items = await db.payments.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    return items


@api.post("/payments")
async def create_payment(body: PaymentInput, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = _uid()
    doc["created_at"] = _now()
    doc["created_by"] = user["email"]
    # USD karşılığı hesapla
    if not doc.get("usd_amount") and doc.get("amount") and doc.get("fx_rate"):
        try:
            # currency=USD ise direkt amount; değilse fx_rate (TL/birim) ile USD'ye çevir
            if (doc.get("currency") or "").upper() == "USD":
                doc["usd_amount"] = float(doc["amount"])
            else:
                # fx_rate currency_to_TL; bir USD'nin TL karşılığı için ek hesap gerek
                usd = await db.currencies.find_one({"code": "USD"}, {"_id": 0})
                usd_rate = (usd or {}).get("rate_to_tl", 0) or 1
                tl_value = float(doc["amount"]) * float(doc["fx_rate"])
                doc["usd_amount"] = tl_value / usd_rate if usd_rate else 0
        except Exception:
            pass
    await db.payments.insert_one(doc)

    # Eğer payable_id varsa borcu güncelle
    if doc.get("payable_id"):
        payable = await db.payables.find_one({"id": doc["payable_id"]}, {"_id": 0})
        if payable:
            paid_sum = await db.payments.aggregate([
                {"$match": {"payable_id": doc["payable_id"]}},
                {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}}}
            ]).to_list(1)
            total_paid = (paid_sum[0]["total"] if paid_sum else 0)
            target = payable.get("usd_amount", 0)
            new_status = "ÖDENDİ" if total_paid >= (target - 0.01) else "KISMİ ÖDEME"
            await db.payables.update_one({"id": doc["payable_id"]}, {"$set": {"status": new_status, "updated_at": _now()}})
    await write_audit(db, user, "create", "payment", doc["id"])
    doc.pop("_id", None)
    return doc


@api.put("/payments/{pid}")
async def update_payment(pid: str, body: PaymentInput, user: dict = Depends(get_current_user)):
    update = body.model_dump(exclude_unset=True)
    update.pop("id", None)
    update["updated_at"] = _now()
    await db.payments.update_one({"id": pid}, {"$set": update})
    await write_audit(db, user, "update", "payment", pid)
    return {"ok": True}


@api.delete("/payments/{pid}")
async def delete_payment(pid: str, user: dict = Depends(get_current_user)):
    await db.payments.delete_one({"id": pid})
    await write_audit(db, user, "delete", "payment", pid)
    return {"ok": True}


# ============================================================
# DASHBOARD & REPORTS
# ============================================================
@api.get("/dashboard/kpi")
async def dashboard_kpi(user: dict = Depends(get_current_user)):
    # Açık borç (PAYABLE, status NOT ÖDENDİ/İPTAL)
    open_payable = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    open_receivable = await db.payables.aggregate([
        {"$match": {"kind": "RECEIVABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)

    today = datetime.now(timezone.utc).date()
    week_later = (today + timedelta(days=7)).isoformat()
    month_later = (today + timedelta(days=30)).isoformat()
    today_iso = today.isoformat()

    week_due = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
                    "due_date": {"$gte": today_iso, "$lte": week_later}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    month_due = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
                    "due_date": {"$gte": today_iso, "$lte": month_later}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    overdue = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
                    "due_date": {"$lt": today_iso}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)

    paid_total = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)

    def g(r):
        if r and r[0]:
            return {"total": float(r[0].get("total", 0) or 0), "count": int(r[0].get("count", 0) or 0)}
        return {"total": 0, "count": 0}

    return {
        "open_payable": g(open_payable),
        "open_receivable": g(open_receivable),
        "net_position": g(open_receivable)["total"] - g(open_payable)["total"],
        "overdue": g(overdue),
        "week_due": g(week_due),
        "month_due": g(month_due),
        "paid_total": g(paid_total),
    }


@api.get("/dashboard/cashflow")
async def dashboard_cashflow(months: int = 12, user: dict = Depends(get_current_user)):
    """Son N ay aylık nakit akış: ödeme + tahsilat (USD)."""
    pipeline = [
        {"$match": {"date": {"$ne": None}}},
        {"$addFields": {"_d": {"$dateFromString": {"dateString": "$date", "onError": None}}}},
        {"$match": {"_d": {"$ne": None}}},
        {"$group": {
            "_id": {"y": {"$year": "$_d"}, "m": {"$month": "$_d"}, "t": "$type"},
            "total": {"$sum": "$usd_amount"}
        }},
        {"$sort": {"_id.y": 1, "_id.m": 1}}
    ]
    rows = await db.payments.aggregate(pipeline).to_list(2000)
    out = {}
    for r in rows:
        key = f"{r['_id']['y']:04d}-{r['_id']['m']:02d}"
        out.setdefault(key, {"month": key, "TEDİYE": 0, "TAHSİL": 0})
        out[key][r['_id']['t']] = float(r["total"] or 0)
    series = list(out.values())
    return series[-months:]


@api.get("/dashboard/by-ship")
async def dashboard_by_ship(user: dict = Depends(get_current_user)):
    rows = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": "$ship", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(50)
    return [{"name": r["_id"] or "Tanımsız", "total": float(r["total"] or 0), "count": r["count"]} for r in rows]


@api.get("/dashboard/by-company")
async def dashboard_by_company(user: dict = Depends(get_current_user)):
    rows = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": "$paying_company", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(50)
    return [{"name": r["_id"] or "Tanımsız", "total": float(r["total"] or 0), "count": r["count"]} for r in rows]


@api.get("/dashboard/by-expense-type")
async def dashboard_by_expense(user: dict = Depends(get_current_user)):
    rows = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE"}},
        {"$group": {"_id": "$expense_type", "total": {"$sum": "$usd_amount"}}},
        {"$sort": {"total": -1}}, {"$limit": 12}
    ]).to_list(20)
    return [{"name": r["_id"] or "Tanımsız", "total": float(r["total"] or 0)} for r in rows]


@api.get("/dashboard/upcoming")
async def dashboard_upcoming(days: int = 30, user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    end = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    items = await db.payables.find({
        "kind": "PAYABLE",
        "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
        "due_date": {"$gte": today, "$lte": end}
    }, {"_id": 0}).sort("due_date", 1).to_list(50)
    return items


@api.get("/dashboard/recent")
async def dashboard_recent(limit: int = 20, user: dict = Depends(get_current_user)):
    items = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


# ============================================================
# CURRENT ACCOUNTS (Cari Hesaplar)
# ============================================================
@api.get("/current-accounts")
async def list_current_accounts(user: dict = Depends(get_current_user)):
    """Her firma/vendor için toplam borç-ödeme ve bakiye."""
    # Borçlar (tedarikçi bazlı toplam)
    payables = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE"}},
        {"$group": {"_id": "$vendor", "borç": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(2000)
    # Ödemeler
    payments = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": "$vendor", "ödeme": {"$sum": "$usd_amount"}}}
    ]).to_list(2000)

    p_map = {p["_id"]: p["ödeme"] for p in payments if p["_id"]}
    result = []
    for row in payables:
        if not row["_id"]:
            continue
        b = float(row["borç"] or 0)
        pd_ = float(p_map.get(row["_id"], 0))
        result.append({
            "name": row["_id"],
            "debt": b,
            "paid": pd_,
            "balance": b - pd_,
            "count": row["count"],
        })
    result.sort(key=lambda x: x["balance"], reverse=True)
    return result


@api.get("/current-accounts/{name}")
async def current_account_detail(name: str, user: dict = Depends(get_current_user)):
    """Bir cari hesabın tüm hareketleri."""
    payables = await db.payables.find({"vendor": name}, {"_id": 0}).sort("due_date", -1).to_list(500)
    payments = await db.payments.find({"vendor": name}, {"_id": 0}).sort("date", -1).to_list(500)
    debt = sum(float(p.get("usd_amount", 0) or 0) for p in payables if p.get("kind") == "PAYABLE")
    paid = sum(float(p.get("usd_amount", 0) or 0) for p in payments if p.get("type") == "TEDİYE")
    return {
        "name": name,
        "summary": {"debt": debt, "paid": paid, "balance": debt - paid},
        "payables": payables,
        "payments": payments
    }


# ============================================================
# CASH & BANK (Kasa & Banka)
# ============================================================
@api.get("/bank-accounts")
async def list_bank_accounts(user: dict = Depends(get_current_user)):
    """Her bankaya göre canlı bakiye (TEDİYE − TAHSİL = net çıkış olarak)."""
    banks = await db.banks.find({}, {"_id": 0}).to_list(500)
    movements = await db.payments.aggregate([
        {"$group": {"_id": {"bank": "$payment_method", "type": "$type"}, "total": {"$sum": "$usd_amount"}}}
    ]).to_list(2000)
    mv = {}
    for m in movements:
        b = m["_id"].get("bank")
        t = m["_id"].get("type")
        if not b:
            continue
        mv.setdefault(b, {"TEDİYE": 0, "TAHSİL": 0})
        mv[b][t] = float(m["total"] or 0)
    result = []
    for b in banks:
        m = mv.get(b["name"], {"TEDİYE": 0, "TAHSİL": 0})
        net = m["TAHSİL"] - m["TEDİYE"]
        result.append({**b, "in": m["TAHSİL"], "out": m["TEDİYE"], "net": net})
    return result


@api.get("/bank-accounts/{bank_name}/transactions")
async def bank_transactions(bank_name: str, user: dict = Depends(get_current_user)):
    items = await db.payments.find({"payment_method": bank_name}, {"_id": 0}).sort("date", -1).to_list(2000)
    return items


# ============================================================
# REPORTS — 12 hazır rapor
# ============================================================
@api.get("/reports/by-ship-detail")
async def report_by_ship(user: dict = Depends(get_current_user)):
    return await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE"}},
        {"$group": {
            "_id": "$ship",
            "total_debt": {"$sum": "$usd_amount"},
            "paid": {"$sum": {"$cond": [{"$eq": ["$status", "ÖDENDİ"]}, "$usd_amount", 0]}},
            "open": {"$sum": {"$cond": [{"$in": ["$status", ["ÖDENDİ", "İPTAL"]]}, 0, "$usd_amount"]}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"total_debt": -1}}
    ]).to_list(100)


@api.get("/reports/aging")
async def report_aging(user: dict = Depends(get_current_user)):
    """Yaşlandırma: 0-30/31-60/61-90/90+ gün."""
    today = datetime.now(timezone.utc).date()
    payables = await db.payables.find({"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$ne": None}}, {"_id": 0}).to_list(5000)
    buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    bucket_counts = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for p in payables:
        try:
            due = datetime.fromisoformat(p["due_date"]).date()
        except Exception:
            continue
        days = (today - due).days
        amt = float(p.get("usd_amount", 0) or 0)
        if days <= 30:
            buckets["0-30"] += amt; bucket_counts["0-30"] += 1
        elif days <= 60:
            buckets["31-60"] += amt; bucket_counts["31-60"] += 1
        elif days <= 90:
            buckets["61-90"] += amt; bucket_counts["61-90"] += 1
        else:
            buckets["90+"] += amt; bucket_counts["90+"] += 1
    return [{"bucket": k, "total": v, "count": bucket_counts[k]} for k, v in buckets.items()]


@api.get("/reports/monthly-projection")
async def report_monthly(months: int = 12, user: dict = Depends(get_current_user)):
    """Sonraki N ay borç projeksiyonu."""
    rows = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$ne": None}}},
        {"$addFields": {"_d": {"$dateFromString": {"dateString": "$due_date", "onError": None}}}},
        {"$match": {"_d": {"$ne": None}}},
        {"$group": {
            "_id": {"y": {"$year": "$_d"}, "m": {"$month": "$_d"}},
            "total": {"$sum": "$usd_amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.y": 1, "_id.m": 1}}
    ]).to_list(100)
    return [{"month": f"{r['_id']['y']:04d}-{r['_id']['m']:02d}", "total": float(r["total"] or 0), "count": r["count"]} for r in rows]


@api.get("/reports/top-vendors")
async def report_top_vendors(limit: int = 20, user: dict = Depends(get_current_user)):
    rows = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": "$vendor", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": limit}
    ]).to_list(50)
    return [{"vendor": r["_id"] or "Tanımsız", "total": float(r["total"] or 0), "count": r["count"]} for r in rows]


@api.get("/reports/by-currency")
async def report_currency_position(user: dict = Depends(get_current_user)):
    rows = await db.payables.aggregate([
        {"$group": {
            "_id": "$currency",
            "borç": {"$sum": {"$cond": [{"$eq": ["$kind", "PAYABLE"]}, "$original_amount", 0]}},
            "alacak": {"$sum": {"$cond": [{"$eq": ["$kind", "RECEIVABLE"]}, "$original_amount", 0]}}
        }}
    ]).to_list(20)
    return [{"currency": r["_id"] or "?", "borç": float(r["borç"] or 0), "alacak": float(r["alacak"] or 0)} for r in rows]


# ============================================================
# NOTIFICATIONS & REMINDERS
# ============================================================
@api.get("/notifications")
async def list_notifications(unread_only: bool = False, user: dict = Depends(get_current_user)):
    q = {"$or": [{"user_id": user["id"]}, {"user_id": None}]}
    if unread_only:
        q["read"] = False
    items = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@api.post("/notifications/{nid}/read")
async def mark_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid}, {"$set": {"read": True, "read_at": _now()}})
    return {"ok": True}


@api.post("/notifications/mark-all-read")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many(
        {"$or": [{"user_id": user["id"]}, {"user_id": None}]},
        {"$set": {"read": True, "read_at": _now()}}
    )
    return {"ok": True}


@api.post("/reminders/check-due")
async def check_due_reminders(background: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Vadesi yaklaşan borçları kontrol et, bildirim oluştur, email gönder."""
    today = datetime.now(timezone.utc).date()
    days_thresholds = [7, 3, 1, 0, -1, -3]  # 0 = bugün, negatif = geçmiş
    created = 0
    for delta in days_thresholds:
        target_date = (today + timedelta(days=delta)).isoformat()
        payables = await db.payables.find({
            "kind": "PAYABLE",
            "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
            "due_date": target_date
        }, {"_id": 0}).to_list(200)
        for p in payables:
            # Aynı borç + aynı eşik için tekrar etme
            existing = await db.notifications.find_one({"resource_id": p["id"], "meta.days_until": delta})
            if existing:
                continue
            title = f"Vade {'yaklaşıyor' if delta > 0 else 'geldi/geçti'}: {p.get('vendor','?')}"
            msg = f"{p.get('vendor')} - {p.get('description','')} - {p.get('usd_amount',0):.2f} USD - Vade: {p.get('due_date')}"
            doc = {
                "id": _uid(),
                "type": "due_reminder",
                "title": title,
                "message": msg,
                "resource": "payable",
                "resource_id": p["id"],
                "user_id": None,  # tüm kullanıcılar
                "meta": {"days_until": delta, "amount": p.get("usd_amount", 0)},
                "read": False,
                "created_at": _now(),
            }
            await db.notifications.insert_one(doc)
            created += 1
            # Email gönder (admin'lere)
            admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1}).to_list(20)
            for a in admins:
                background.add_task(send_payment_reminder, a["email"], p, delta)
    return {"created": created}


# ============================================================
# AUDIT LOG
# ============================================================
@api.get("/audit-logs")
async def list_audit(limit: int = 200, user: dict = Depends(require_admin)):
    items = await db.audit_logs.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
    return items


# ============================================================
# FX (Döviz Kurları)
# ============================================================
@api.get("/fx/latest")
async def latest_fx(user: dict = Depends(get_current_user)):
    rows = await db.currencies.find({}, {"_id": 0}).to_list(50)
    return rows


@api.get("/fx/history")
async def fx_history(code: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if code: q["code"] = code
    return await db.fx_rates.find(q, {"_id": 0}).sort("date", -1).to_list(500)


@api.post("/fx/refresh")
async def refresh_fx(user: dict = Depends(get_current_user)):
    """TCMB'den canlı kur çek + DB'yi güncelle."""
    result = await update_fx_in_db(db)
    await write_audit(db, user, "refresh", "fx", meta=result)
    return result


@api.get("/fx/on-date")
async def fx_on_date(code: str, date: str, user: dict = Depends(get_current_user)):
    """Belirli bir tarihteki kuru getir (kur sabitleme için)."""
    # Önce o tarihte var mı?
    rec = await db.fx_rates.find_one({"code": code, "date": {"$regex": f"^{date[:10]}"}}, {"_id": 0})
    if rec:
        return {"code": code, "date": rec.get("date"), "rate_to_tl": rec.get("rate_to_tl"), "source": "archive"}
    # Yoksa güncel currencies'tan döndür
    cur = await db.currencies.find_one({"code": code}, {"_id": 0})
    if cur:
        return {"code": code, "date": cur.get("last_updated"), "rate_to_tl": cur.get("rate_to_tl"), "source": "latest"}
    return {"code": code, "date": None, "rate_to_tl": 0, "source": "none"}


# ============================================================
# FILE UPLOADS — Fatura/Dekont eklemek için
# ============================================================
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"}
MIME_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


@api.post("/uploads")
async def upload_file(
    file: UploadFile = File(...),
    attached_to: Optional[str] = Form(None),  # "payable" / "payment" / "general"
    attached_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen format: {file.content_type}. PDF, JPG, PNG, WEBP kabul edilir.")
    ext = MIME_EXT.get(file.content_type, "bin")
    fid = _uid()
    fname = f"{fid}.{ext}"
    fpath = UPLOAD_DIR / fname
    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:  # 15MB
        raise HTTPException(status_code=400, detail="Dosya çok büyük (max 15MB)")
    async with aiofiles.open(fpath, "wb") as f:
        await f.write(contents)
    doc = {
        "id": fid,
        "filename": file.filename,
        "stored_as": fname,
        "mime": file.content_type,
        "size": len(contents),
        "attached_to": attached_to,
        "attached_id": attached_id,
        "uploaded_by": user["email"],
        "created_at": _now(),
    }
    await db.uploads.insert_one(doc)
    # İlgili borç/ödemeye dosya referansını ekle
    if attached_to == "payable" and attached_id:
        await db.payables.update_one({"id": attached_id}, {"$push": {"attachments": fid}})
    elif attached_to == "payment" and attached_id:
        await db.payments.update_one({"id": attached_id}, {"$push": {"attachments": fid}})
    await write_audit(db, user, "upload", "file", fid, {"filename": file.filename, "attached_to": attached_to})
    doc.pop("_id", None)
    return doc


@api.get("/uploads/{file_id}")
async def get_upload(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.uploads.find_one({"id": file_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    fpath = UPLOAD_DIR / doc["stored_as"]
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Dosya diskte yok")
    return FileResponse(str(fpath), media_type=doc.get("mime"), filename=doc.get("filename"))


@api.get("/uploads/by-resource/{resource}/{resource_id}")
async def uploads_by_resource(resource: str, resource_id: str, user: dict = Depends(get_current_user)):
    items = await db.uploads.find({"attached_to": resource, "attached_id": resource_id}, {"_id": 0}).to_list(50)
    return items


@api.delete("/uploads/{file_id}")
async def delete_upload(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.uploads.find_one({"id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Dosya yok")
    fpath = UPLOAD_DIR / doc["stored_as"]
    if fpath.exists():
        try: fpath.unlink()
        except Exception: pass
    await db.uploads.delete_one({"id": file_id})
    # İlgili koleksiyondan da pull et
    if doc.get("attached_to") == "payable" and doc.get("attached_id"):
        await db.payables.update_one({"id": doc["attached_id"]}, {"$pull": {"attachments": file_id}})
    elif doc.get("attached_to") == "payment" and doc.get("attached_id"):
        await db.payments.update_one({"id": doc["attached_id"]}, {"$pull": {"attachments": file_id}})
    await write_audit(db, user, "delete", "file", file_id)
    return {"ok": True}


# ============================================================
# OCR — Fatura okuma
# ============================================================
@api.post("/ocr/invoice")
async def ocr_invoice_endpoint(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        raise HTTPException(status_code=400, detail="JPG/PNG/WEBP/PDF dosyası gerekli")
    # Geçici diske yaz
    ext = MIME_EXT.get(file.content_type, "jpg")
    tmp_path = UPLOAD_DIR / f"ocr_tmp_{_uid()}.{ext}"
    contents = await file.read()
    async with aiofiles.open(tmp_path, "wb") as f:
        await f.write(contents)
    try:
        parsed = await ocr_invoice(str(tmp_path), file.content_type)
        await write_audit(db, user, "ocr", "invoice", meta={"vendor": parsed.get("vendor")})
        return parsed
    finally:
        try: tmp_path.unlink()
        except Exception: pass


# ============================================================
# AI ASSISTANT — Function-calling pattern (context-injected)
# ============================================================
async def _build_assistant_context() -> dict:
    """Asistana sunulacak güncel finansal veriyi MongoDB'den topla."""
    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()
    week = (today + timedelta(days=7)).isoformat()
    month = (today + timedelta(days=30)).isoformat()

    # KPI
    open_p = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    open_r = await db.payables.aggregate([
        {"$match": {"kind": "RECEIVABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    overdue = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$lt": today_iso}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    week_due = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$gte": today_iso, "$lte": week}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    month_due = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$gte": today_iso, "$lte": month}}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    paid_total = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": None, "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)

    def g(r):
        if r and r[0]: return {"total": float(r[0].get("total", 0) or 0), "count": int(r[0].get("count", 0) or 0)}
        return {"total": 0, "count": 0}

    # Gemi/şirket/masraf
    by_ship = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}}},
        {"$group": {"_id": "$ship", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(20)
    by_company = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": "$paying_company", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(20)
    by_expense = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE"}},
        {"$group": {"_id": "$expense_type", "total": {"$sum": "$usd_amount"}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(20)
    top_vendors = await db.payments.aggregate([
        {"$match": {"type": "TEDİYE"}},
        {"$group": {"_id": "$vendor", "total": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 15}
    ]).to_list(20)

    # Yaşlandırma
    aging_raw = await db.payables.find(
        {"kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]}, "due_date": {"$ne": None}},
        {"_id": 0, "due_date": 1, "usd_amount": 1}
    ).to_list(5000)
    buckets = {"0-30": [0, 0], "31-60": [0, 0], "61-90": [0, 0], "90+": [0, 0]}
    for p in aging_raw:
        try: due = datetime.fromisoformat(p["due_date"]).date()
        except Exception: continue
        days = (today - due).days
        amt = float(p.get("usd_amount", 0) or 0)
        if days <= 30: buckets["0-30"][0] += amt; buckets["0-30"][1] += 1
        elif days <= 60: buckets["31-60"][0] += amt; buckets["31-60"][1] += 1
        elif days <= 90: buckets["61-90"][0] += amt; buckets["61-90"][1] += 1
        else: buckets["90+"][0] += amt; buckets["90+"][1] += 1

    upcoming = await db.payables.find({
        "kind": "PAYABLE", "status": {"$nin": ["ÖDENDİ", "İPTAL"]},
        "due_date": {"$gte": today_iso, "$lte": month}
    }, {"_id": 0}).sort("due_date", 1).to_list(20)

    recent_payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(25)

    cashflow = await db.payments.aggregate([
        {"$match": {"date": {"$ne": None}}},
        {"$addFields": {"_d": {"$dateFromString": {"dateString": "$date", "onError": None}}}},
        {"$match": {"_d": {"$ne": None}}},
        {"$group": {"_id": {"y": {"$year": "$_d"}, "m": {"$month": "$_d"}, "t": "$type"}, "total": {"$sum": "$usd_amount"}}},
        {"$sort": {"_id.y": 1, "_id.m": 1}}
    ]).to_list(200)
    cf_map = {}
    for r in cashflow:
        k = f"{r['_id']['y']:04d}-{r['_id']['m']:02d}"
        cf_map.setdefault(k, {"month": k, "TEDİYE": 0, "TAHSİL": 0})
        cf_map[k][r['_id']['t']] = float(r["total"] or 0)
    monthly_cashflow = list(cf_map.values())[-12:]

    fx_latest = await db.currencies.find({}, {"_id": 0}).to_list(20)

    by_currency = await db.payables.aggregate([
        {"$group": {
            "_id": "$currency",
            "borç": {"$sum": {"$cond": [{"$eq": ["$kind", "PAYABLE"]}, "$original_amount", 0]}},
            "alacak": {"$sum": {"$cond": [{"$eq": ["$kind", "RECEIVABLE"]}, "$original_amount", 0]}}
        }}
    ]).to_list(20)

    return {
        "kpi": {
            "open_payable": g(open_p), "open_receivable": g(open_r),
            "overdue": g(overdue), "week_due": g(week_due), "month_due": g(month_due),
            "paid_total": g(paid_total),
        },
        "by_ship": [{"name": r["_id"] or "Tanımsız", "total": r["total"], "count": r["count"]} for r in by_ship],
        "by_company": [{"name": r["_id"] or "Tanımsız", "total": r["total"], "count": r["count"]} for r in by_company],
        "by_expense": [{"name": r["_id"] or "Tanımsız", "total": r["total"]} for r in by_expense],
        "top_vendors": [{"vendor": r["_id"] or "Tanımsız", "total": r["total"], "count": r["count"]} for r in top_vendors],
        "aging": [{"bucket": k, "total": v[0], "count": v[1]} for k, v in buckets.items()],
        "upcoming": upcoming,
        "recent_payments": recent_payments,
        "monthly_cashflow": monthly_cashflow,
        "fx_latest": fx_latest,
        "by_currency": [{"currency": r["_id"], "borç": r["borç"], "alacak": r["alacak"]} for r in by_currency],
    }


class ChatInput(BaseModel):
    session_id: Optional[str] = None
    message: str


@api.post("/ai/chat")
async def ai_chat(body: ChatInput, user: dict = Depends(get_current_user)):
    sid = body.session_id or _uid()
    # History çek
    history_docs = await db.ai_messages.find({"session_id": sid}, {"_id": 0}).sort("created_at", 1).to_list(50)
    history = [{"role": h["role"], "content": h["content"]} for h in history_docs]
    # Context'i topla
    context = await _build_assistant_context()
    # User message kaydet
    await db.ai_messages.insert_one({
        "id": _uid(), "session_id": sid, "user_id": user["id"],
        "role": "user", "content": body.message, "created_at": _now()
    })
    # AI cevap
    response = await chat_with_assistant(sid, body.message, context, history)
    # AI cevap kaydet
    await db.ai_messages.insert_one({
        "id": _uid(), "session_id": sid, "user_id": user["id"],
        "role": "assistant", "content": response, "created_at": _now()
    })
    # Session header
    await db.ai_sessions.update_one(
        {"id": sid},
        {"$set": {"id": sid, "user_id": user["id"], "last_message": body.message[:120], "updated_at": _now()},
         "$setOnInsert": {"created_at": _now(), "title": body.message[:60]}},
        upsert=True,
    )
    return {"session_id": sid, "response": response}


@api.get("/ai/sessions")
async def list_ai_sessions(user: dict = Depends(get_current_user)):
    items = await db.ai_sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(50)
    return items


@api.get("/ai/sessions/{sid}/messages")
async def ai_session_messages(sid: str, user: dict = Depends(get_current_user)):
    items = await db.ai_messages.find({"session_id": sid, "user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return items


@api.delete("/ai/sessions/{sid}")
async def delete_ai_session(sid: str, user: dict = Depends(get_current_user)):
    await db.ai_sessions.delete_one({"id": sid, "user_id": user["id"]})
    await db.ai_messages.delete_many({"session_id": sid, "user_id": user["id"]})
    return {"ok": True}


# ============================================================
# Mount + Startup
# ============================================================
app.include_router(api)

scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup_event():
    await ensure_indexes(db)
    # Admin seed
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@eyfinans.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin1234!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": _uid(),
            "email": admin_email,
            "name": "Admin",
            "role": "admin",
            "password_hash": hash_password(admin_password),
            "active": True,
            "created_at": _now(),
        })
        logger.info("Admin user oluşturuldu: %s", admin_email)
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info("Admin şifresi güncellendi")
    # Veri seed
    await seed_all(db)

    # TCMB ilk çekme (varsa atla — seed verisi var, en azından bir defa canlı dene)
    try:
        await update_fx_in_db(db)
    except Exception as e:
        logger.warning("İlk TCMB fetch başarısız: %s", e)

    # Scheduler — her gün 15:30 (TCMB bültenleri 15:30 sonrası yayımlanır)
    try:
        scheduler.add_job(update_fx_in_db, "cron", hour=15, minute=30, args=[db], id="tcmb_daily", replace_existing=True)
        scheduler.start()
        logger.info("TCMB scheduler aktif (her gün 15:30)")
    except Exception as e:
        logger.warning("Scheduler başlatılamadı: %s", e)

    logger.info("Startup tamam")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        scheduler.shutdown(wait=False)
    except Exception: pass
    client.close()


@api.get("/")
async def root():
    return {"name": "EY Finans Platform API", "version": "1.0.0"}
