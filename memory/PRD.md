# EY Finans Platform — PRD

## Original Problem Statement
Excel'de yönetilen denizcilik şirketi finansal süreçlerini (KURLAR16.xlsm + EY Ödeme Tablosu16.xlsm) tek bir web uygulamasına dönüştürmek. Borç/alacak girişi, hatırlatmalar, güçlü raporlama, sade modern Apple/Notion tasarım, mobil değil web odaklı, parametrik (her şey master data'dan yönetilebilir).

## Architecture
- **Backend:** FastAPI + Motor (async MongoDB) — 1280 LOC (server.py + ai_service + fx_service + email_service + auth_utils + seed_loader)
- **Auth:** JWT (PyJWT + bcrypt) email+password, 7d token, httpOnly cookie + Bearer header, brute-force lockout
- **Email:** Resend (asyncio.to_thread) — payment reminders, password reset
- **AI:** Emergent LLM Key + GPT-5.2 (OCR vision + finansal asistan, context-injected RAG)
- **FX:** TCMB XML live scraper + APScheduler cron (15:30 Europe/Istanbul) + kur sabitleme
- **File Storage:** Local disk `/app/backend/uploads/` + MongoDB metadata
- **Frontend:** React 18 + Tailwind + shadcn/ui + Recharts + Lucide + Sonner
- **Design:** Apple/Notion vibe — Geist font, slide-over panels, soft shadows, monochrome charts

### Iteration 3 — AI Action Engine & Branding Cleanup
- **AI Aksiyon Engine** — 4 hazır aksiyon (`create_payable`, `create_payment`, `mark_payable_paid`, `send_summary_email`) · confirm-then-execute pattern (pending → completed/rejected/failed) · idempotency · `created_by_ai=true` flag
- **System prompt:** AI sorgu modu (text) ile aksiyon modu (JSON action) arasında otomatik karar verir
- **Frontend ActionCard:** "AKSIYON ÖNERISI" başlık + params tablosu + Onayla/İptal butonları + status badge'leri (yeşil completed / gri rejected)
- **Branding cleanup:** Tüm UI'dan "GPT-5.2" mention'ları kaldırıldı → "Akıllı asistan" yazıyor
- **Emergent badge:** display:none ile gizlendi
- ✅ 12/12 pytest + frontend E2E PASS · 0 critical issues

## Implemented (Jan 2026)
### Iteration 1 — Core MVP (11 modules)
- JWT auth, user management, audit log
- 13 master data collections (parametric)
- Payables/Receivables/Payments full CRUD
- Dashboard (6 KPI + 5 charts), 5 reports, current accounts, cash & bank
- Notifications + reminder check-due
- Excel seed (778 vendors, 24 ships, 38 banks, 127 payments, 85 payables...)
- Apple/Notion design system
- ✅ 47/47 pytest + frontend E2E PASS

### Iteration 2 — AI & Smart Features
- **File Uploads** — PDF/JPG/PNG/WEBP upload (max 15MB), attached_to/attached_id pattern (borç/ödeme), download via blob, audit log
- **OCR (GPT-5.2 Vision)** — fatura görselinden vendor/invoice_no/dates/amount/currency/description otomatik parse, form auto-fill
- **TCMB Live FX** — `www.tcmb.gov.tr/kurlar/today.xml` real-time scrape, APScheduler cron her gün 15:30 İstanbul, manuel "Şimdi Güncelle" butonu, kur sabitleme `/fx/on-date`
- **AI Asistan (RAG)** — GPT-5.2, context-injected (KPI + by_ship + by_company + top_vendors + aging + upcoming + recent + cashflow + FX + currency position), Turkish UI/system prompt, session management, gerçek sayısal cevaplar
- ✅ 17/17 pytest + frontend E2E PASS · 0 critical issues

## User Personas
1. Süper Admin · 2. Yönetici · 3. Muhasebe · 4. Finans · 5. Operasyon · 6. İzleyici

## Modules (Final State)
| # | Modül | Endpoints | Frontend |
|---|---|---|---|
| 1 | Dashboard | /dashboard/kpi+cashflow+by-ship+by-company+by-expense-type+upcoming+recent | ✅ |
| 2 | Borçlar (Payables) | /payables CRUD | ✅ + OCR + Ekler |
| 3 | Alacaklar | /payables?kind=RECEIVABLE | ✅ |
| 4 | Ödemeler | /payments CRUD | ✅ |
| 5 | Kasa & Banka | /bank-accounts + transactions | ✅ |
| 6 | Cari Hesaplar | /current-accounts + detail | ✅ |
| 7 | Raporlar | /reports/{by-ship,aging,monthly,top-vendors,by-currency} | ✅ |
| 8 | **AI Asistan** | /ai/chat + /ai/sessions | ✅ |
| 9 | Hatırlatmalar | /notifications + /reminders/check-due | ✅ |
| 10 | Tanımlamalar | /master/{collection} (13 koleksiyon) | ✅ |
| 11 | Kullanıcılar | /users + /audit-logs | ✅ |
| 12 | Ayarlar | profile + TCMB refresh | ✅ |

## Backlog (Next)
- ⏳ split server.py into routers (already 1280 LOC)
- Excel toplu import (CSV upload)
- Daily/weekly summary email cron
- Recurring/installment payables
- Bank statement reconciliation
- Dark mode toggle
- ⌘K command palette (currently visual)

## Tech Notes
- `EMERGENT_LLM_KEY` .env'de — GPT-5.2 ücretsiz
- TCMB: APScheduler + pytz Europe/Istanbul (her gün 15:30)
- Uploads: 15MB cap, allowed: jpeg/png/webp/pdf
- AI context her chat'te yeniden hesaplanır → her zaman güncel veri
- Login: admin@eyfinans.com / Admin1234!
