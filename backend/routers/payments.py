"""Payments router."""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from database import db
from dependencies import get_current_user, write_audit, _uid, _now

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Optional[str] = "TEDİYE"
    date: Optional[str] = None
    payable_id: Optional[str] = None
    ship: Optional[str] = None
    vendor: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None
    paying_company: Optional[str] = None
    payment_method: Optional[str] = None
    amount: Optional[float] = 0
    currency: Optional[str] = "USD"
    fx_rate: Optional[float] = 1
    usd_amount: Optional[float] = 0
    approved: Optional[bool] = False


@router.get("")
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
    return await db.payments.find(q, {"_id": 0}).sort("date", -1).to_list(limit)


@router.post("")
async def create_payment(body: PaymentInput, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = _uid()
    doc["created_at"] = _now()
    doc["created_by"] = user["email"]
    if not doc.get("usd_amount") and doc.get("amount") and doc.get("fx_rate"):
        try:
            if (doc.get("currency") or "").upper() == "USD":
                doc["usd_amount"] = float(doc["amount"])
            else:
                usd = await db.currencies.find_one({"code": "USD"}, {"_id": 0})
                usd_rate = (usd or {}).get("rate_to_tl", 0) or 1
                tl_value = float(doc["amount"]) * float(doc["fx_rate"])
                doc["usd_amount"] = tl_value / usd_rate if usd_rate else 0
        except Exception:
            pass
    await db.payments.insert_one(doc)

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
    await write_audit(user, "create", "payment", doc["id"])
    doc.pop("_id", None)
    return doc


@router.put("/{pid}")
async def update_payment(pid: str, body: PaymentInput, user: dict = Depends(get_current_user)):
    update = body.model_dump(exclude_unset=True)
    update.pop("id", None)
    update["updated_at"] = _now()
    await db.payments.update_one({"id": pid}, {"$set": update})
    await write_audit(user, "update", "payment", pid)
    return {"ok": True}


@router.delete("/{pid}")
async def delete_payment(pid: str, user: dict = Depends(get_current_user)):
    await db.payments.delete_one({"id": pid})
    await write_audit(user, "delete", "payment", pid)
    return {"ok": True}
