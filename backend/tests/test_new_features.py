"""Tests for iter_2 new features: file uploads, OCR, TCMB FX refresh, AI assistant.
Also includes a smoke regression for auth + dashboard.
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://data-review-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@eyfinans.com"
ADMIN_PASSWORD = "Admin1234!"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("token")
    return data["token"]


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ===== SMOKE: auth + dashboard regression =====
class TestSmoke:
    def test_auth_me(self, headers):
        r = requests.get(f"{API}/auth/me", headers=headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_dashboard_kpi(self, headers):
        r = requests.get(f"{API}/dashboard/kpi", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["open_payable", "open_receivable", "overdue", "week_due", "month_due", "paid_total"]:
            assert k in d, f"missing {k}"


# ===== File Uploads =====
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa15\xc8\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestUploads:
    payable_id = None
    upload_id = None

    def test_get_a_payable(self, headers):
        r = requests.get(f"{API}/payables?limit=1", headers=headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0, "no payables in seed"
        TestUploads.payable_id = items[0]["id"]

    def test_upload_file_attached_to_payable(self, headers):
        assert TestUploads.payable_id
        files = {"file": ("test_TEST.png", io.BytesIO(PNG_1x1), "image/png")}
        data = {"attached_to": "payable", "attached_id": TestUploads.payable_id}
        r = requests.post(f"{API}/uploads", files=files, data=data, headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["mime"] == "image/png"
        assert j["filename"] == "test_TEST.png"
        assert j["attached_to"] == "payable"
        assert j["attached_id"] == TestUploads.payable_id
        TestUploads.upload_id = j["id"]

    def test_list_uploads_by_resource(self, headers):
        r = requests.get(
            f"{API}/uploads/by-resource/payable/{TestUploads.payable_id}",
            headers=headers, timeout=30,
        )
        assert r.status_code == 200
        items = r.json()
        ids = [i["id"] for i in items]
        assert TestUploads.upload_id in ids

    def test_get_upload_file(self, headers):
        r = requests.get(f"{API}/uploads/{TestUploads.upload_id}", headers=headers, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 50

    def test_reject_invalid_mime(self, headers):
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(f"{API}/uploads", files=files, headers=headers, timeout=30)
        assert r.status_code == 400

    def test_delete_upload(self, headers):
        r = requests.delete(f"{API}/uploads/{TestUploads.upload_id}", headers=headers, timeout=30)
        assert r.status_code == 200
        # verify gone
        r2 = requests.get(f"{API}/uploads/{TestUploads.upload_id}", headers=headers, timeout=30)
        assert r2.status_code == 404


# ===== FX (TCMB) =====
class TestFX:
    def test_refresh_fx(self, headers):
        r = requests.post(f"{API}/fx/refresh", headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert j.get("updated", 0) >= 5
        assert j.get("date")

    def test_fx_latest_has_recent_update(self, headers):
        r = requests.get(f"{API}/fx/latest", headers=headers, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        usd = next((x for x in rows if x.get("code") == "USD"), None)
        assert usd, "USD missing"
        assert usd.get("rate_to_tl", 0) > 0
        assert usd.get("last_updated")

    def test_fx_on_date(self, headers):
        r = requests.get(f"{API}/fx/on-date?code=USD&date=2026-01-15", headers=headers, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j.get("code") == "USD"
        assert j.get("source") in ("archive", "latest", "none")
        assert j.get("rate_to_tl", 0) > 0


# ===== OCR =====
class TestOCR:
    def test_ocr_invoice_endpoint_accepts_image(self, headers):
        """OCR with tiny PNG. AI may return empty/error but endpoint should not 5xx."""
        files = {"file": ("invoice.png", io.BytesIO(PNG_1x1), "image/png")}
        r = requests.post(f"{API}/ocr/invoice", files=files, headers=headers, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j, dict)
        # Either parsed JSON with some keys, or an error/empty dict (model can't parse 1x1)
        if "error" in j:
            pytest.skip(f"OCR returned error (expected for 1x1 dummy): {j['error']}")

    def test_ocr_rejects_invalid_mime(self, headers):
        files = {"file": ("x.txt", io.BytesIO(b"not an invoice"), "text/plain")}
        r = requests.post(f"{API}/ocr/invoice", files=files, headers=headers, timeout=30)
        assert r.status_code == 400


# ===== AI Assistant =====
class TestAIAssistant:
    session_id = None

    def test_chat_creates_session_and_responds(self, headers):
        r = requests.post(
            f"{API}/ai/chat",
            json={"message": "Bu ay vadesi gelen toplam borç ne kadar?"},
            headers=headers, timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("session_id")
        assert isinstance(j.get("response"), str) and len(j["response"]) > 5
        TestAIAssistant.session_id = j["session_id"]

    def test_chat_continues_session(self, headers):
        assert TestAIAssistant.session_id
        r = requests.post(
            f"{API}/ai/chat",
            json={"message": "En yüksek 5 tedarikçi kim?", "session_id": TestAIAssistant.session_id},
            headers=headers, timeout=180,
        )
        assert r.status_code == 200
        j = r.json()
        assert j["session_id"] == TestAIAssistant.session_id
        assert len(j["response"]) > 5

    def test_list_sessions(self, headers):
        r = requests.get(f"{API}/ai/sessions", headers=headers, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert any(s["id"] == TestAIAssistant.session_id for s in rows)

    def test_get_session_messages(self, headers):
        r = requests.get(f"{API}/ai/sessions/{TestAIAssistant.session_id}/messages", headers=headers, timeout=30)
        assert r.status_code == 200
        msgs = r.json()
        # 2 user + 2 assistant from above 2 chats
        roles = [m["role"] for m in msgs]
        assert roles.count("user") == 2
        assert roles.count("assistant") == 2

    def test_delete_session(self, headers):
        r = requests.delete(f"{API}/ai/sessions/{TestAIAssistant.session_id}", headers=headers, timeout=30)
        assert r.status_code == 200
        # confirm messages cleared
        r2 = requests.get(f"{API}/ai/sessions/{TestAIAssistant.session_id}/messages", headers=headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json() == []
