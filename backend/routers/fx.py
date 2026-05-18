"""FX (Döviz Kurları) router."""
from typing import Optional
from fastapi import APIRouter, Depends
from database import db
from dependencies import get_current_user, write_audit
from fx_service import update_fx_in_db

router = APIRouter(prefix="/fx", tags=["fx"])


@router.get("/latest")
async def latest_fx(user: dict = Depends(get_current_user)):
    return await db.currencies.find({}, {"_id": 0}).to_list(50)


@router.get("/history")
async def fx_history(code: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if code: q["code"] = code
    return await db.fx_rates.find(q, {"_id": 0}).sort("date", -1).to_list(500)


@router.post("/refresh")
async def refresh_fx(user: dict = Depends(get_current_user)):
    result = await update_fx_in_db(db)
    await write_audit(user, "refresh", "fx", meta=result)
    return result


@router.get("/on-date")
async def fx_on_date(code: str, date: str, user: dict = Depends(get_current_user)):
    rec = await db.fx_rates.find_one({"code": code, "date": {"$regex": f"^{date[:10]}"}}, {"_id": 0})
    if rec:
        return {"code": code, "date": rec.get("date"), "rate_to_tl": rec.get("rate_to_tl"), "source": "archive"}
    cur = await db.currencies.find_one({"code": code}, {"_id": 0})
    if cur:
        return {"code": code, "date": cur.get("last_updated"), "rate_to_tl": cur.get("rate_to_tl"), "source": "latest"}
    return {"code": code, "date": None, "rate_to_tl": 0, "source": "none"}
