from __future__ import annotations

import hashlib
import hmac
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from server.billing_service import RateLimiter, create_server
from server.provider_adapters import verify_standard_webhook
import base64
import time


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

    def test_payment_order_requires_authenticated_account(self) -> None:
        status, registered = self.request("POST", "/v1/auth/register", {"email": "orders@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        status, order = self.request(
            "POST",
            "/v1/orders",
            {"order_id": "order-123", "plan": "Solo"},
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(order["account_id"], registered["account_id"])

    def test_hosted_credit_consumption_is_idempotent(self) -> None:
        status, registered = self.request("POST", "/v1/auth/register", {"email": "credits@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        account_id = registered["account_id"]
        token = registered["access_token"]
        webhook = {"event_id": "credit-plan-1", "account_id": account_id, "plan": "Solo", "status": "active", "expires_at": "2099-01-01T00:00:00Z"}
        raw = json.dumps(webhook).encode("utf-8")
        signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        status, _ = self.request("POST", "/v1/webhooks/polar", webhook, headers={"X-Bookmark-Intelligence-Signature": f"sha256={signature}"})
        self.assertEqual(status, 200)

        headers = {"Authorization": f"Bearer {token}"}
        status, first = self.request("POST", "/v1/usage/consume", {"units": 3, "request_id": "summary-1"}, headers=headers)
        self.assertEqual(status, 200)
        self.assertFalse(first["duplicate"])
        self.assertEqual(first["remaining"], 297)
        status, duplicate = self.request("POST", "/v1/usage/consume", {"units": 3, "request_id": "summary-1"}, headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["remaining"], 297)
        status, insufficient = self.request("POST", "/v1/usage/consume", {"units": 400, "request_id": "summary-too-large"}, headers=headers)
        self.assertEqual(status, 402)
        self.assertFalse(insufficient["ok"])

    def test_standard_webhook_signature(self) -> None:
        secret = base64.b64encode(b"polar-secret").decode("ascii")
        body = b'{"type":"subscription.active"}'
        webhook_id = "msg_123"
        timestamp = str(int(time.time()))
        signed = f"{webhook_id}.{timestamp}.".encode("utf-8") + body
        signature = base64.b64encode(hmac.new(b"polar-secret", signed, hashlib.sha256).digest()).decode("ascii")
        verify_standard_webhook(secret, body, {"webhook-id": webhook_id, "webhook-timestamp": timestamp, "webhook-signature": f"v1,{signature}"})

    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = RateLimiter()
        self.assertTrue(limiter.allow("127.0.0.1", "test", 2))
        self.assertTrue(limiter.allow("127.0.0.1", "test", 2))
        self.assertFalse(limiter.allow("127.0.0.1", "test", 2))

    def test_polar_standard_event_updates_entitlement(self) -> None:
        from server.billing_service import BillingService

        service = BillingService(Path(self.tempdir.name) / "polar.sqlite3", base64.b64encode(b"polar-secret").decode("ascii"))
        registered = service.register("polar@example.com", "a-long-test-password")
        payload = {
            "type": "subscription.active",
            "timestamp": "2099-01-01T00:00:00Z",
            "data": {
                "id": "sub_123",
                "current_period_end": "2099-12-31T00:00:00Z",
                "metadata": {"account_id": registered["account_id"], "plan": "Solo"},
            },
        }
        raw = json.dumps(payload).encode("utf-8")
        webhook_id = "msg_polar"
        timestamp = str(int(time.time()))
        signed = f"{webhook_id}.{timestamp}.".encode("utf-8") + raw
        signature = base64.b64encode(hmac.new(b"polar-secret", signed, hashlib.sha256).digest()).decode("ascii")
        result = service.apply_polar_webhook(payload, raw, {
            "webhook-id": webhook_id,
            "webhook-timestamp": timestamp,
            "webhook-signature": f"v1,{signature}",
        })
        self.assertFalse(result["duplicate"])
        self.assertEqual(service.entitlement(registered["account_id"], registered["access_token"])["plan"], "Solo")


if __name__ == "__main__":
    unittest.main()
