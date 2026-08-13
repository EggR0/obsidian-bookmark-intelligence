from __future__ import annotations

import hashlib
import hmac
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from server.billing_service import create_server


class BillingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, Path(self.tempdir.name) / "billing.sqlite3", "test-webhook-secret")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, data

    def test_login_entitlement_and_idempotent_webhook(self) -> None:
        status, registered = self.request("POST", "/v1/auth/register", {"email": "user@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        self.assertTrue(registered["access_token"])
        account_id = registered["account_id"]
        token = registered["access_token"]

        status, free = self.request("GET", f"/v1/entitlements/{account_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, 200)
        self.assertEqual(free["plan"], "Free")
        self.assertEqual(free["features"], [])

        webhook = {"event_id": "evt-1", "account_id": account_id, "plan": "Solo", "status": "active", "expires_at": "2099-01-01T00:00:00Z"}
        raw = json.dumps(webhook).encode("utf-8")
        signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        status, applied = self.request("POST", "/v1/webhooks/polar", webhook, headers={"X-Bookmark-Intelligence-Signature": f"sha256={signature}"})
        self.assertEqual(status, 200)
        self.assertFalse(applied["duplicate"])

        status, solo = self.request("GET", f"/v1/entitlements/{account_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, 200)
        self.assertEqual(solo["plan"], "Solo")
        self.assertIn("backup", solo["features"])

        status, duplicate = self.request("POST", "/v1/webhooks/polar", webhook, headers={"X-Bookmark-Intelligence-Signature": f"sha256={signature}"})
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])

    def test_invalid_webhook_signature_is_rejected(self) -> None:
        status, payload = self.request("POST", "/v1/webhooks/toss", {"event_id": "evt-1", "account_id": "unknown"}, headers={"X-Bookmark-Intelligence-Signature": "bad"})
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
