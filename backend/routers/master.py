"""Master data router — parametrik referans verileri (generic CRUD)."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from database import db
from dependencies import get_current_user, write_audit, _uid, _now

router = APIRouter(prefix="/master", tags=["master"])

MASTER_COLLECTIONS = {
    "companies", "armators", "managers", "ships", "people", "countries",
    "banks", "expense_types", "accounting_codes", "vendors", "currencies",
    "payment_statuses", "payment_methods",
}


class MasterItem(BaseModel):
    model_config = ConfigDict(extra="allow")


def _check_collection(collection: str):
    if collection not in MASTER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Bilinmeyen koleksiyon")


@router.get("/{collection}")
async def list_master(collection: str, user: dict = Depends(get_current_user)):
    _check_collection(collection)
    return await db[collection].find({}, {"_id": 0}).sort("created_at", 1).to_list(5000)


@router.post("/{collection}")
async def create_master(collection: str, body: MasterItem, user: dict = Depends(get_current_user)):
    _check_collection(collection)
    doc = body.model_dump()
    doc["id"] = _uid()
    doc["active"] = doc.get("active", True)
    doc["created_at"] = _now()
    await db[collection].insert_one(doc)
    await write_audit(user, "create", collection, doc["id"])
    doc.pop("_id", None)
    return doc


@router.put("/{collection}/{item_id}")
async def update_master(collection: str, item_id: str, body: MasterItem, user: dict = Depends(get_current_user)):
    _check_collection(collection)
    update = body.model_dump(exclude_unset=True)
    update.pop("id", None); update.pop("_id", None); update.pop("created_at", None)
    if not update:
        return {"ok": True}
    update["updated_at"] = _now()
    await db[collection].update_one({"id": item_id}, {"$set": update})
    await write_audit(user, "update", collection, item_id)
    return {"ok": True}


@router.delete("/{collection}/{item_id}")
async def delete_master(collection: str, item_id: str, user: dict = Depends(get_current_user)):
    _check_collection(collection)
    await db[collection].delete_one({"id": item_id})
    await write_audit(user, "delete", collection, item_id)
    return {"ok": True}
