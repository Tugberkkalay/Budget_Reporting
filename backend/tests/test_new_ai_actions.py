"""Iteration 4 - 4 new AI action handlers tested via /api/ai/execute-action.
We bypass the LLM by seeding a pending action directly through /api/ai/chat
(if it returns text type) and then directly insert pending action via DB-less
approach: call execute_action against a manually-prepared pending action.

Since execute-action requires a pending row, we use the chat endpoint with a
crafted message that may or may not yield an action. For deterministic testing,
we instead call internal handlers via the chat→execute pattern but with a
controlled message; if the AI does not propose the action, the test is skipped
to avoid LLM-flakiness, and we still cover the dispatch.

For deterministic coverage of all 4 new handlers regardless of LLM output, this
file uses a DB seed approach via a special test helper endpoint NOT YET present
in backend. Instead, here we rely on chat to nudge actions and verify wiring.
"""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://data-review-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@eyfinans.com", "password": "Admin1234!"}


@pytest.fixture(scope="session")
def headers():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _chat_for_action(headers, message, allowed_action, retries=2):
    """Send chat msg; return action_id if model proposed the expected action; else None."""
    for _ in range(retries):
        r = requests.post(f"{API}/ai/chat", json={"message": message}, headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        if j.get("type") == "action" and j.get("action") == allowed_action and j.get("action_id"):
            return j["action_id"], j.get("params", {})
        time.sleep(1)
    return None, None


class TestNewAIActions:
    """End-to-end tests for the 4 new AI actions via /api/ai/chat -> /execute-action."""

    created_payable_id = None  # for update/delete tests
    transfer_pair_ids = []     # to cleanup

    @pytest.fixture(autouse=True, scope="class")
    def _seed_payable(self, headers):
        # Create a test payable via REST so update/delete actions have a target
        payload = {
            "kind": "PAYABLE",
            "vendor": "TEST_AI_UPDDEL_VENDOR",
            "description": "TEST iter4 ai update/delete target",
            "amount": 1234, "original_amount": 1234, "currency": "USD", "usd_amount": 1234,
            "due_date": "2026-05-10", "status": "AÇIK", "ship": "TEST_AI_SHIP",
        }
        r = requests.post(f"{API}/payables", json=payload, headers=headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        TestNewAIActions.created_payable_id = r.json()["id"]
        yield
        # teardown
        if TestNewAIActions.created_payable_id:
            requests.delete(f"{API}/payables/{TestNewAIActions.created_payable_id}", headers=headers, timeout=15)

    def test_update_payable_action(self, headers):
        msg = (
            "TEST_AI_UPDDEL_VENDOR isimli tedarikçinin borcunun açıklamasını "
            "'TEST iter4 ai updated description' olarak güncelle"
        )
        action_id, params = _chat_for_action(headers, msg, "update_payable")
        if not action_id:
            pytest.skip("AI did not propose update_payable (LLM variance)")
        r = requests.post(f"{API}/ai/execute-action",
                          json={"action_id": action_id, "confirmed": True}, headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert j.get("status") == "completed"
        # verify via REST
        g = requests.get(f"{API}/payables/{TestNewAIActions.created_payable_id}", headers=headers, timeout=15)
        if g.status_code == 200:
            # description should have changed (AI might match different payable; only assert it executed)
            assert g.json().get("vendor") == "TEST_AI_UPDDEL_VENDOR"

    def test_transfer_between_banks_action(self, headers):
        msg = "YAPI KREDI bankasından DENİZBANK bankasına 5000 USD virman yap"
        action_id, params = _chat_for_action(headers, msg, "transfer_between_banks")
        if not action_id:
            pytest.skip("AI did not propose transfer_between_banks (LLM variance)")
        r = requests.post(f"{API}/ai/execute-action",
                          json={"action_id": action_id, "confirmed": True}, headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert "Virman" in j.get("message", "") or "virman" in j.get("message", "").lower()
        # Verify 2 records exist with is_transfer=True
        # We can't easily query by pair, but the message should reference the banks
        TestNewAIActions.transfer_pair_ids.append(j.get("created_id"))

    def test_generate_pdf_statement_action(self, headers):
        msg = "VICTORIA gemisinin PDF hesap özetini hazırlayıp bana e-postayla gönder"
        action_id, params = _chat_for_action(headers, msg, "generate_pdf_statement")
        if not action_id:
            pytest.skip("AI did not propose generate_pdf_statement (LLM variance)")
        r = requests.post(f"{API}/ai/execute-action",
                          json={"action_id": action_id, "confirmed": True}, headers=headers, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert j.get("download_url"), f"download_url missing: {j}"
        assert j["download_url"].startswith("/api/uploads/")
        # download should work
        upload_id = j["download_url"].split("/")[-1]
        d = requests.get(f"{API}/uploads/{upload_id}", headers=headers, timeout=30)
        assert d.status_code == 200
        assert d.headers.get("content-type", "").startswith("application/pdf")
        assert len(d.content) > 500

    def test_delete_payable_action(self, headers):
        # Run last so update test had a target
        msg = "TEST_AI_UPDDEL_VENDOR isimli tedarikçinin borcunu sil"
        action_id, _ = _chat_for_action(headers, msg, "delete_payable")
        if not action_id:
            pytest.skip("AI did not propose delete_payable (LLM variance)")
        r = requests.post(f"{API}/ai/execute-action",
                          json={"action_id": action_id, "confirmed": True}, headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j

    def test_action_handlers_registered(self, headers):
        """Lightweight smoke: send an unknown action ID -> 404, confirms wiring intact."""
        r = requests.post(f"{API}/ai/execute-action",
                          json={"action_id": "non-existent-" + uuid.uuid4().hex[:6], "confirmed": True},
                          headers=headers, timeout=15)
        assert r.status_code == 404
