"""Current accounts + Bank accounts routers."""
from fastapi import APIRouter, Depends
from database import db
from dependencies import get_current_user

router = APIRouter(tags=["accounts"])


@router.get("/current-accounts")
async def list_current_accounts(user: dict = Depends(get_current_user)):
    payables = await db.payables.aggregate([
        {"$match": {"kind": "PAYABLE"}},
        {"$group": {"_id": "$vendor", "borç": {"$sum": "$usd_amount"}, "count": {"$sum": 1}}}
    ]).to_list(2000)
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
        result.append({"name": row["_id"], "debt": b, "paid": pd_, "balance": b - pd_, "count": row["count"]})
    result.sort(key=lambda x: x["balance"], reverse=True)
    return result


@router.get("/current-accounts/{name}")
async def current_account_detail(name: str, user: dict = Depends(get_current_user)):
    payables = await db.payables.find({"vendor": name}, {"_id": 0}).sort("due_date", -1).to_list(500)
    payments = await db.payments.find({"vendor": name}, {"_id": 0}).sort("date", -1).to_list(500)
    debt = sum(float(p.get("usd_amount", 0) or 0) for p in payables if p.get("kind") == "PAYABLE")
    paid = sum(float(p.get("usd_amount", 0) or 0) for p in payments if p.get("type") == "TEDİYE")
    return {
        "name": name,
        "summary": {"debt": debt, "paid": paid, "balance": debt - paid},
        "payables": payables, "payments": payments
    }


@router.get("/bank-accounts")
async def list_bank_accounts(user: dict = Depends(get_current_user)):
    banks = await db.banks.find({}, {"_id": 0}).to_list(500)
    movements = await db.payments.aggregate([
        {"$group": {"_id": {"bank": "$payment_method", "type": "$type"}, "total": {"$sum": "$usd_amount"}}}
    ]).to_list(2000)
    mv = {}
    for m in movements:
        b = m["_id"].get("bank")
        t = m["_id"].get("type")
        if not b: continue
        mv.setdefault(b, {"TEDİYE": 0, "TAHSİL": 0})
        mv[b][t] = float(m["total"] or 0)
    result = []
    for b in banks:
        m = mv.get(b["name"], {"TEDİYE": 0, "TAHSİL": 0})
        net = m["TAHSİL"] - m["TEDİYE"]
        result.append({**b, "in": m["TAHSİL"], "out": m["TEDİYE"], "net": net})
    return result


@router.get("/bank-accounts/{bank_name}/transactions")
async def bank_transactions(bank_name: str, user: dict = Depends(get_current_user)):
    return await db.payments.find({"payment_method": bank_name}, {"_id": 0}).sort("date", -1).to_list(2000)
