"""TCMB döviz kuru servisi — XML endpoint scrape."""
import logging
import uuid
import httpx
from datetime import datetime, timezone
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"


async def fetch_tcmb_rates() -> List[Dict[str, Any]]:
    """TCMB'den anlık döviz kurlarını çeker."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(TCMB_URL)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            date_attr = root.attrib.get("Date") or root.attrib.get("Tarih")
            results = []
            for cur in root.findall("Currency"):
                code = cur.attrib.get("CurrencyCode")
                unit = float(cur.attrib.get("Unit", "1") or 1)
                name = (cur.findtext("Isim") or "").strip()
                forex_buying = cur.findtext("ForexBuying")
                forex_selling = cur.findtext("ForexSelling")
                banknote_buying = cur.findtext("BanknoteBuying")
                banknote_selling = cur.findtext("BanknoteSelling")

                def f(v):
                    try: return float(v) / unit if v else 0
                    except: return 0

                results.append({
                    "code": code,
                    "name": name,
                    "unit": unit,
                    "rate_to_tl": f(forex_buying),
                    "forex_buying": f(forex_buying),
                    "forex_selling": f(forex_selling),
                    "banknote_buying": f(banknote_buying),
                    "banknote_selling": f(banknote_selling),
                    "date": date_attr,
                })
            return results
    except Exception as e:
        logger.exception("TCMB çekme hatası")
        return []


async def update_fx_in_db(db) -> dict:
    """TCMB'den çek + DB'ye yaz (currencies tablosu + fx_rates arşiv)."""
    rates = await fetch_tcmb_rates()
    if not rates:
        return {"ok": False, "updated": 0, "error": "TCMB'ye ulaşılamadı"}

    today_iso = datetime.now(timezone.utc).isoformat()
    updated = 0
    for r in rates:
        if not r.get("code") or r.get("rate_to_tl", 0) <= 0:
            continue
        # Güncel currencies tablosunu güncelle
        await db.currencies.update_one(
            {"code": r["code"]},
            {"$set": {
                "code": r["code"],
                "name": r["name"],
                "rate_to_tl": r["rate_to_tl"],
                "forex_selling": r["forex_selling"],
                "banknote_buying": r["banknote_buying"],
                "banknote_selling": r["banknote_selling"],
                "last_updated": today_iso,
                "active": True,
            },
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": today_iso}},
            upsert=True
        )
        # Tarihsel arşiv
        await db.fx_rates.update_one(
            {"code": r["code"], "date": r["date"]},
            {"$set": {**r, "updated_at": today_iso},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": today_iso}},
            upsert=True
        )
        updated += 1
    # TL için 1 olduğundan emin ol
    await db.currencies.update_one(
        {"code": "TL"},
        {"$set": {"code": "TL", "name": "Türk Lirası", "rate_to_tl": 1, "last_updated": today_iso, "active": True},
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": today_iso}},
        upsert=True
    )
    logger.info("TCMB güncelleme tamam: %d kur", updated)
    return {"ok": True, "updated": updated, "date": rates[0].get("date") if rates else None}
