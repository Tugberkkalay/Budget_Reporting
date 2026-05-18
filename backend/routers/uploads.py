"""File uploads router (fatura/dekont) + OCR endpoint."""
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
import aiofiles
from database import db
from dependencies import get_current_user, write_audit, _uid, _now
from ai_service import ocr_invoice

router = APIRouter(tags=["uploads"])

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"}
MIME_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


@router.post("/uploads")
async def upload_file(
    file: UploadFile = File(...),
    attached_to: Optional[str] = Form(None),
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
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dosya çok büyük (max 15MB)")
    async with aiofiles.open(fpath, "wb") as f:
        await f.write(contents)
    doc = {
        "id": fid, "filename": file.filename, "stored_as": fname,
        "mime": file.content_type, "size": len(contents),
        "attached_to": attached_to, "attached_id": attached_id,
        "uploaded_by": user["email"], "created_at": _now(),
    }
    await db.uploads.insert_one(doc)
    if attached_to == "payable" and attached_id:
        await db.payables.update_one({"id": attached_id}, {"$push": {"attachments": fid}})
    elif attached_to == "payment" and attached_id:
        await db.payments.update_one({"id": attached_id}, {"$push": {"attachments": fid}})
    await write_audit(user, "upload", "file", fid, {"filename": file.filename, "attached_to": attached_to})
    doc.pop("_id", None)
    return doc


@router.get("/uploads/{file_id}")
async def get_upload(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.uploads.find_one({"id": file_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    fpath = UPLOAD_DIR / doc["stored_as"]
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Dosya diskte yok")
    return FileResponse(str(fpath), media_type=doc.get("mime"), filename=doc.get("filename"))


@router.get("/uploads/by-resource/{resource}/{resource_id}")
async def uploads_by_resource(resource: str, resource_id: str, user: dict = Depends(get_current_user)):
    return await db.uploads.find({"attached_to": resource, "attached_id": resource_id}, {"_id": 0}).to_list(50)


@router.delete("/uploads/{file_id}")
async def delete_upload(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.uploads.find_one({"id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Dosya yok")
    fpath = UPLOAD_DIR / doc["stored_as"]
    if fpath.exists():
        try: fpath.unlink()
        except Exception: pass
    await db.uploads.delete_one({"id": file_id})
    if doc.get("attached_to") == "payable" and doc.get("attached_id"):
        await db.payables.update_one({"id": doc["attached_id"]}, {"$pull": {"attachments": file_id}})
    elif doc.get("attached_to") == "payment" and doc.get("attached_id"):
        await db.payments.update_one({"id": doc["attached_id"]}, {"$pull": {"attachments": file_id}})
    await write_audit(user, "delete", "file", file_id)
    return {"ok": True}


@router.post("/ocr/invoice")
async def ocr_invoice_endpoint(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        raise HTTPException(status_code=400, detail="JPG/PNG/WEBP/PDF dosyası gerekli")
    ext = MIME_EXT.get(file.content_type, "jpg")
    tmp_path = UPLOAD_DIR / f"ocr_tmp_{_uid()}.{ext}"
    contents = await file.read()
    async with aiofiles.open(tmp_path, "wb") as f:
        await f.write(contents)
    try:
        parsed = await ocr_invoice(str(tmp_path), file.content_type)
        await write_audit(user, "ocr", "invoice", meta={"vendor": parsed.get("vendor")})
        return parsed
    finally:
        try: tmp_path.unlink()
        except Exception: pass
