"""
EY Finans Backend API Tests
Comprehensive pytest suite for all 11 modules and integration flows.
Run: pytest /app/backend/tests/backend_test.py -v --tb=short --junitxml=/app/test_reports/pytest/pytest_results.xml
"""
import os
import time
import uuid
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://data-review-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@eyfinans.com"
ADMIN_PASSWORD = "Admin1234!"


# ---- Fixtures ----
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_session(session):
    r = session.post(f"{API}/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token")
    assert token
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


# ============ AUTH ============
class TestAuth:
    def test_login_success(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d
        assert d["email"] == ADMIN_EMAIL
        assert d.get("role") == "admin"
        # cookie set
        assert "access_token" in session.cookies.get_dict() or r.cookies.get("access_token")

    def test_login_wrong_password(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"email": ADMIN_EMAIL, "password": "WRONG"})
        assert r.status_code in (400, 401, 403)

    def test_auth_me_with_bearer(self, auth_session):
        r = auth_session.get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        assert r.json().get("email") == ADMIN_EMAIL

    def test_no_auth_protected(self):
        r = requests.get(f"{API}/users")
        assert r.status_code in (401, 403)


# ============ DASHBOARD ============
class TestDashboard:
    def test_kpi(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/kpi")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["open_payable", "open_receivable", "net_position",
                  "overdue", "week_due", "month_due", "paid_total"]:
            assert k in d, f"Missing {k}"

    def test_cashflow(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/cashflow")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_by_ship(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/by-ship")
        assert r.status_code == 200

    def test_by_company(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/by-company")
        assert r.status_code == 200

    def test_by_expense_type(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/by-expense-type")
        assert r.status_code == 200

    def test_upcoming(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/upcoming")
        assert r.status_code == 200

    def test_recent(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/recent")
        assert r.status_code == 200


# ============ PAYABLES ============
class TestPayables:
    created_id = None

    def test_list_payables(self, auth_session):
        r = auth_session.get(f"{API}/payables", params={"kind": "PAYABLE"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Seeded ~85 records expected
        assert len(data) >= 1

    def test_list_receivables(self, auth_session):
        r = auth_session.get(f"{API}/payables", params={"kind": "RECEIVABLE"})
        assert r.status_code == 200

    def test_search_filter(self, auth_session):
        r = auth_session.get(f"{API}/payables", params={"q": "a"})
        assert r.status_code == 200

    def test_create_payable_persist(self, auth_session):
        payload = {
            "kind": "PAYABLE",
            "vendor": "TEST_VENDOR_ABC",
            "description": "TEST payable for pytest",
            "amount": 1000,
            "currency": "USD",
            "usd_amount": 1000,
            "due_date": "2026-03-15",
            "status": "AÇIK",
            "ship": "TEST_SHIP"
        }
        r = auth_session.post(f"{API}/payables", json=payload)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("vendor") == "TEST_VENDOR_ABC"
        assert "id" in d
        # auto year/month
        assert d.get("year") == 2026
        assert d.get("month") == 3
        TestPayables.created_id = d["id"]

        # GET to verify persistence
        g = auth_session.get(f"{API}/payables/{d['id']}")
        assert g.status_code == 200
        assert g.json().get("vendor") == "TEST_VENDOR_ABC"

    def test_update_payable(self, auth_session):
        assert TestPayables.created_id
        r = auth_session.put(f"{API}/payables/{TestPayables.created_id}",
                             json={"description": "TEST updated"})
        assert r.status_code == 200
        g = auth_session.get(f"{API}/payables/{TestPayables.created_id}")
        assert g.json().get("description") == "TEST updated"


# ============ PAYMENTS + INTEGRATION ============
class TestPayments:
    created_payable = None
    created_payment = None

    def test_list_payments(self, auth_session):
        r = auth_session.get(f"{API}/payments")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_filter_by_type(self, auth_session):
        r = auth_session.get(f"{API}/payments", params={"type": "TEDİYE"})
        assert r.status_code == 200

    def test_payable_payment_integration(self, auth_session):
        """Create payable -> create payment for it -> assert status changes."""
        pay = {
            "kind": "PAYABLE",
            "vendor": "TEST_INTEG_VENDOR",
            "description": "TEST integration payable",
            "amount": 500, "currency": "USD", "usd_amount": 500,
            "due_date": "2026-04-20", "status": "AÇIK"
        }
        rp = auth_session.post(f"{API}/payables", json=pay)
        assert rp.status_code in (200, 201), rp.text
        payable_id = rp.json()["id"]
        TestPayments.created_payable = payable_id

        # Full payment
        pmt = {
            "type": "TEDİYE",
            "vendor": "TEST_INTEG_VENDOR",
            "amount": 500, "currency": "USD", "usd_amount": 500,
            "fx_rate": 1, "date": "2026-04-15",
            "payable_id": payable_id, "bank": "TEST_BANK"
        }
        rm = auth_session.post(f"{API}/payments", json=pmt)
        assert rm.status_code in (200, 201), rm.text
        TestPayments.created_payment = rm.json().get("id")

        # Verify payable status auto-updated
        g = auth_session.get(f"{API}/payables/{payable_id}")
        st = g.json().get("status")
        assert st in ("ÖDENDİ", "KISMİ ÖDEME"), f"Expected ÖDENDİ/KISMİ, got {st}"

    def test_cleanup_integration(self, auth_session):
        if TestPayments.created_payment:
            auth_session.delete(f"{API}/payments/{TestPayments.created_payment}")
        if TestPayments.created_payable:
            auth_session.delete(f"{API}/payables/{TestPayments.created_payable}")
        if TestPayables.created_id:
            auth_session.delete(f"{API}/payables/{TestPayables.created_id}")


# ============ CURRENT ACCOUNTS ============
class TestCurrentAccounts:
    def test_list(self, auth_session):
        r = auth_session.get(f"{API}/current-accounts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============ BANK ACCOUNTS ============
class TestBanks:
    def test_list_banks(self, auth_session):
        r = auth_session.get(f"{API}/bank-accounts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============ REPORTS ============
class TestReports:
    @pytest.mark.parametrize("path", [
        "by-ship-detail", "aging", "monthly-projection",
        "top-vendors", "by-currency"
    ])
    def test_reports(self, auth_session, path):
        r = auth_session.get(f"{API}/reports/{path}")
        assert r.status_code == 200, f"{path}: {r.text}"


# ============ MASTER DATA ============
class TestMaster:
    COLLECTIONS = ["companies", "ships", "vendors", "banks", "expense_types",
                   "accounting_codes", "currencies", "payment_statuses",
                   "payment_methods", "armators", "managers", "people", "countries"]

    @pytest.mark.parametrize("c", COLLECTIONS)
    def test_list_collection(self, auth_session, c):
        r = auth_session.get(f"{API}/master/{c}")
        assert r.status_code == 200, f"{c}: {r.text}"
        assert isinstance(r.json(), list)

    def test_crud_vendors(self, auth_session):
        name = f"TEST_VENDOR_{uuid.uuid4().hex[:6]}"
        r = auth_session.post(f"{API}/master/vendors", json={"name": name})
        assert r.status_code in (200, 201), r.text
        item_id = r.json().get("id")
        assert item_id

        # update
        r2 = auth_session.put(f"{API}/master/vendors/{item_id}",
                              json={"name": name + "_UPD"})
        assert r2.status_code == 200

        # delete
        r3 = auth_session.delete(f"{API}/master/vendors/{item_id}")
        assert r3.status_code in (200, 204)


# ============ NOTIFICATIONS / REMINDERS ============
class TestReminders:
    def test_check_due(self, auth_session):
        r = auth_session.post(f"{API}/reminders/check-due")
        assert r.status_code == 200, r.text

    def test_notifications_list(self, auth_session):
        r = auth_session.get(f"{API}/notifications")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_mark_all_read(self, auth_session):
        r = auth_session.post(f"{API}/notifications/mark-all-read")
        assert r.status_code == 200


# ============ USERS (admin) ============
class TestUsers:
    def test_list_users(self, auth_session):
        r = auth_session.get(f"{API}/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_audit_logs(self, auth_session):
        r = auth_session.get(f"{API}/audit-logs")
        assert r.status_code == 200


# ============ FX ============
class TestFx:
    def test_fx_latest(self, auth_session):
        r = auth_session.get(f"{API}/fx/latest")
        assert r.status_code == 200, r.text
        data = r.json()
        # Could be dict or list, accept either
        if isinstance(data, dict) and "rates" in data:
            data = data["rates"]
        assert data, "FX empty"
