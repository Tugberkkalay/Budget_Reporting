"""Iteration 3 — AI action engine + branding cleanup regression tests."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    # Try frontend/.env
    from pathlib import Path
    fe = Path("/app/frontend/.env").read_text()
    for line in fe.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE = line.split("=", 1)[1].strip()
            break
BASE = BASE.rstrip("/")

ADMIN = {"email": "admin@eyfinans.com", "password": "Admin1234!"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- REGRESSION (smoke) ----------
class TestRegression:
    def test_login(self, token):
        assert token

    def test_dashboard_kpi(self, h):
        r = requests.get(f"{BASE}/api/dashboard/kpi", headers=h, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "open_payable" in d and "overdue" in d

    def test_payables_list(self, h):
        r = requests.get(f"{BASE}/api/payables?kind=PAYABLE&limit=5", headers=h, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ships(self, h):
        r = requests.get(f"{BASE}/api/master/ships", headers=h, timeout=20)
        assert r.status_code == 200

    def test_fx_latest(self, h):
        r = requests.get(f"{BASE}/api/fx/latest", headers=h, timeout=20)
        assert r.status_code == 200

    def test_ocr_mime_validation(self, h):
        files = {"file": ("a.txt", b"hello", "text/plain")}
        r = requests.post(f"{BASE}/api/ocr/invoice", headers={"Authorization": h["Authorization"]}, files=files, timeout=20)
        assert r.status_code == 400


# ---------- AI CHAT — TEXT (query) mode ----------
class TestAIChatText:
    def test_text_query_returns_numeric(self, h):
        r = requests.post(f"{BASE}/api/ai/chat", headers=h,
                          json={"message": "Vadesi geçmiş borçların toplamı kaç USD?"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("type") == "text"
        assert isinstance(d.get("response"), str) and len(d["response"]) > 0
        assert "session_id" in d


# ---------- AI CHAT — ACTION mode + EXECUTE ----------
class TestAIActions:
    def test_create_payable_action_flow(self, h):
        msg = "VICTORIA için VERGİ borcu ekle 50000 USD vade 30 Mart 2026 açıklama TEST_iter3 vergi"
        r = requests.post(f"{BASE}/api/ai/chat", headers=h, json={"message": msg}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        # AI ya action ya text döner — eğer text dönerse zorunlu alan eksik diye soruyor
        if d.get("type") != "action":
            pytest.skip(f"AI did not return action type, got: {d.get('type')} -> {d.get('response')[:200]}")
        assert d.get("action") == "create_payable"
        assert d.get("action_id")
        params = d.get("params") or {}
        assert params.get("vendor") or params.get("ship")  # at least one set
        action_id = d["action_id"]

        # Execute
        r2 = requests.post(f"{BASE}/api/ai/execute-action", headers=h,
                           json={"action_id": action_id, "confirmed": True}, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("status") == "completed", d2
        created_id = d2.get("created_id")
        assert created_id

        # Verify in payables list with created_by_ai=true
        r3 = requests.get(f"{BASE}/api/payables/{created_id}", headers=h, timeout=20)
        assert r3.status_code == 200
        p = r3.json()
        assert p.get("created_by_ai") is True
        assert p.get("kind") == "PAYABLE"

        # Idempotency — second execute should fail (already completed)
        r4 = requests.post(f"{BASE}/api/ai/execute-action", headers=h,
                           json={"action_id": action_id, "confirmed": True}, timeout=30)
        assert r4.status_code == 400

        # Cleanup
        requests.delete(f"{BASE}/api/payables/{created_id}", headers=h, timeout=20)

    def test_action_reject_flow(self, h):
        msg = "MORNING için MALZEME borcu ekle 12000 USD vade 15 Nisan 2026 TEST_iter3"
        r = requests.post(f"{BASE}/api/ai/chat", headers=h, json={"message": msg}, timeout=120)
        d = r.json()
        if d.get("type") != "action":
            pytest.skip("AI did not return action — model dependent")
        action_id = d["action_id"]
        r2 = requests.post(f"{BASE}/api/ai/execute-action", headers=h,
                           json={"action_id": action_id, "confirmed": False}, timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("status") == "rejected"

    def test_send_summary_email_action(self, h):
        msg = "Vadesi geçmiş borçların özet emailini bana gönder"
        r = requests.post(f"{BASE}/api/ai/chat", headers=h, json={"message": msg}, timeout=120)
        d = r.json()
        if d.get("type") != "action":
            pytest.skip("AI returned text instead of action — acceptable")
        assert d.get("action") == "send_summary_email"
        r2 = requests.post(f"{BASE}/api/ai/execute-action", headers=h,
                           json={"action_id": d["action_id"], "confirmed": True}, timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("status") == "completed"

    def test_session_messages_include_action_fields(self, h):
        # Trigger an action
        msg = "CENDA için YAKIT borcu 8000 EUR vade 10 Mayıs 2026 TEST_iter3"
        r = requests.post(f"{BASE}/api/ai/chat", headers=h, json={"message": msg}, timeout=120)
        d = r.json()
        sid = d.get("session_id")
        assert sid
        # Wait & fetch
        time.sleep(0.5)
        r2 = requests.get(f"{BASE}/api/ai/sessions/{sid}/messages", headers=h, timeout=20)
        assert r2.status_code == 200
        msgs = r2.json()
        if d.get("type") == "action":
            proposals = [m for m in msgs if m.get("message_type") == "action_proposal"]
            assert proposals, "No action_proposal message stored"
            ap = proposals[0]
            assert ap.get("action_id") and ap.get("action") and ap.get("params") is not None

    def test_execute_invalid_action_id(self, h):
        r = requests.post(f"{BASE}/api/ai/execute-action", headers=h,
                          json={"action_id": "non-existent-id-xyz", "confirmed": True}, timeout=15)
        assert r.status_code == 404
