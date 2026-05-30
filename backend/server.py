"""MARTI Denizcilik Finans Platform — FastAPI backend (modular).
Routers'a ayrıldı: auth, users, master, payables, payments, dashboard,
accounts, reports, notifications, fx, uploads, ai.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import db, client
from dependencies import _uid, _now
from auth_utils import hash_password, verify_password
from seed_loader import seed_all, ensure_indexes
from fx_service import update_fx_in_db

# Routers
from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.master import router as master_router
from routers.payables import router as payables_router
from routers.payments import router as payments_router
from routers.dashboard import router as dashboard_router
from routers.accounts import router as accounts_router
from routers.reports import router as reports_router
from routers.notifications import router as notifications_router
from routers.fx import router as fx_router
from routers.uploads import router as uploads_router
from routers.ai import router as ai_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MARTI Denizcilik Finans API")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers under /api
api.include_router(auth_router)
api.include_router(users_router)
api.include_router(master_router)
api.include_router(payables_router)
api.include_router(payments_router)
api.include_router(dashboard_router)
api.include_router(accounts_router)
api.include_router(reports_router)
api.include_router(notifications_router)
api.include_router(fx_router)
api.include_router(uploads_router)
api.include_router(ai_router)


@api.get("/")
async def root():
    return {"name": "MARTI Denizcilik Finans API", "version": "2.0.0"}


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
            "id": _uid(), "email": admin_email, "name": "Admin", "role": "admin",
            "password_hash": hash_password(admin_password), "active": True, "created_at": _now(),
        })
        logger.info("Admin user oluşturuldu: %s", admin_email)
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info("Admin şifresi güncellendi")

    await seed_all(db)

    try:
        await update_fx_in_db(db)
    except Exception as e:
        logger.warning("İlk TCMB fetch başarısız: %s", e)

    try:
        from pytz import timezone as _tz
        scheduler.add_job(update_fx_in_db, "cron", hour=15, minute=30,
                          timezone=_tz("Europe/Istanbul"), args=[db],
                          id="tcmb_daily", replace_existing=True)
        scheduler.start()
        logger.info("TCMB scheduler aktif (her gün 15:30 Europe/Istanbul)")
    except Exception as e:
        logger.warning("Scheduler başlatılamadı: %s", e)

    logger.info("Startup tamam")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()
