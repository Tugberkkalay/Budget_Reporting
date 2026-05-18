# EY Finans Platform — PRD

## Original Problem Statement
Excel'de yönetilen denizcilik şirketi finansal süreçlerini (KURLAR16.xlsm + EY Ödeme Tablosu16.xlsm) tek bir web uygulamasına dönüştürmek. Borç/alacak girişi, hatırlatmalar, güçlü raporlama, sade modern Apple/Notion tasarım, mobil değil web odaklı, parametrik (her şey master data'dan yönetilebilir).

## Architecture
- **Backend:** FastAPI + Motor (async MongoDB) — 945 LOC single server.py
- **Auth:** JWT (PyJWT + bcrypt) email+password, 7 day token, httpOnly cookie + Bearer header, brute-force lockout 5/15min
- **Email:** Resend (asyncio.to_thread) — payment reminders, password reset
- **Frontend:** React 18 + Tailwind + shadcn/ui + Recharts + Lucide + Sonner
- **Design:** Apple/Notion vibe — light theme, Geist font, slide-over panels, soft shadows, monochrome charts
- **DB:** MongoDB (`ey_finans_db`) — 18 collections with uuid `id` field, no ObjectId in responses

## User Personas
1. **Süper Admin** — full access, user management, audit logs
2. **Yönetici** — approves payments, sees all data
3. **Muhasebe** — enters payables/payments
4. **Finans** — reports + approval
5. **Operasyon** — restricted to own ship
6. **İzleyici** — read only

## Core Requirements (Static)
- 11 modules (Dashboard, Borçlar, Alacaklar, Ödemeler, Kasa&Banka, Cari Hesaplar, Raporlar, Hatırlatmalar, Tanımlamalar, Kullanıcılar, Ayarlar)
- Parametric master data (13 collections — no hardcoding)
- Multi-company, multi-ship, multi-currency support
- Real Excel data seeded at startup
- Turkish UI, English API

## Implemented (Jan 2026)
### Backend
- [x] JWT auth (login, me, logout, forgot/reset-password)
- [x] User CRUD (admin only) + role-based access
- [x] Generic master data CRUD for 13 collections
- [x] Payables/Receivables CRUD (kind discriminator)
- [x] Payments CRUD with auto-status update (full→ÖDENDİ, partial→KISMİ ÖDEME)
- [x] Dashboard endpoints (kpi, cashflow, by-ship, by-company, by-expense-type, upcoming, recent)
- [x] Reports (by-ship-detail, aging 0/30/60/90+, monthly-projection, top-vendors, by-currency)
- [x] Current Accounts list + detail
- [x] Bank Accounts list + transactions
- [x] Notifications + reminder check-due endpoint
- [x] Audit log endpoint (admin only)
- [x] FX rates endpoints
- [x] Excel data seed (778 vendors, 24 ships, 38 banks, 53 expense types, 101 accounting codes, 127 payments, 85 payables, 31 FX rates) — idempotent
- [x] Brute-force protection + MongoDB indexes (TTL on password tokens)

### Frontend
- [x] Login page (Apple-style, dark CTA, soft inputs)
- [x] Layout — Notion-style collapsible sidebar + glassmorphism topbar with bell, avatar, ⌘K search
- [x] Dashboard — 6 KPI cards + 5 charts + upcoming/recent tables + TCMB widget
- [x] Payables page — list, search, filters, slide-over CRUD form
- [x] Receivables page — kind=RECEIVABLE variant
- [x] Payments page — list, filters, slide-over CRUD form
- [x] Cash & Bank — accounts list + transactions detail with in/out/net
- [x] Current Accounts — vendor list + detail (borç/ödeme history)
- [x] Reports — 5 templates with charts (bar, pie, table)
- [x] Reminders — notification list + mark-read + check-due trigger
- [x] Master Data — 13 collections with generic CRUD UI
- [x] Users (admin) — user CRUD + audit log side panel
- [x] Settings — profile, notification prefs, system info

### Testing
- [x] 47/47 pytest cases PASSED
- [x] Playwright E2E: login → dashboard → all 11 modules navigate, slide-overs open, logout works
- [x] data-testid attributes on all critical UI

## Known Polish Items (Non-blocking)
- server.py is 945 lines — could split into modules
- CORS_ORIGINS="*" needs tightening in production
- Master data POST does not enforce unique names (acceptable for parametric lookups)

## Backlog (P1 — Next Iterations)
- File upload (fatura/dekont PDF/JPG) for payables
- Excel import for bulk payables
- CSV/PDF export per page
- Recurring payables (monthly rent, salary auto-generation)
- Installment splitter (1 debt → N installments)
- Bank statement reconciliation (CSV upload → auto-match)
- Daily/weekly summary email cron
- TCMB live FX puller (currently seed only)
- Account statement PDF email to vendor
- Dark mode toggle
- ⌘K command palette functionality (currently visual only)
- Audit log filterable UI

## Backlog (P2)
- OCR fatura okuma
- AI assistant ("Bu ay MARTI ne kadar ödedi?")
- Banka API entegrasyonu (YKB / Denizbank ekstre)
- E-Fatura GİB entegrasyonu
- Sözleşme yönetimi modülü
- Bütçe vs gerçekleşen karşılaştırma
- 2FA opsiyonu

## Tech Notes
- Frontend: REACT_APP_BACKEND_URL kullanılmalı (production preview URL)
- Backend: MONGO_URL + DB_NAME, JWT_SECRET, ADMIN_EMAIL/PASSWORD, RESEND_API_KEY, SENDER_EMAIL .env'de
- Tüm endpoint'ler /api prefix'i ile (Kubernetes ingress kuralı)
- Frontend axios `withCredentials: true` + Bearer fallback header
- Seed idempotent — server her başlatıldığında veri varsa atlar
