from __future__ import annotations

import hashlib
import hmac
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

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

    def test_billing_page_is_served(self) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", "/billing")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn("Create account", body)
        self.assertIn("/v1/checkouts", body)

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

    def test_team_member_shares_owner_entitlement_and_credits(self) -> None:
        status, owner = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        status, member = self.request("POST", "/v1/auth/register", {"email": "member@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        webhook = {"event_id": "team-plan-1", "account_id": owner["account_id"], "plan": "Team", "status": "active", "expires_at": "2099-01-01T00:00:00Z"}
        raw = json.dumps(webhook).encode("utf-8")
        signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        status, _ = self.request("POST", "/v1/webhooks/polar", webhook, headers={"X-Bookmark-Intelligence-Signature": f"sha256={signature}"})
        self.assertEqual(status, 200)

        status, added = self.request(
            "POST", "/v1/team/members", {"member_account_id": member["account_id"]},
            headers={"Authorization": f"Bearer {owner['access_token']}"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(added["plan"], "Team")
        status, member_entitlement = self.request(
            "GET", f"/v1/entitlements/{member['account_id']}",
            headers={"Authorization": f"Bearer {member['access_token']}"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(member_entitlement["plan"], "Team")
        self.assertEqual(member_entitlement["owner_account_id"], owner["account_id"])
        status, consumed = self.request(
            "POST", "/v1/usage/consume", {"units": 2, "request_id": "member-summary"},
            headers={"Authorization": f"Bearer {member['access_token']}"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(consumed["remaining"], 798)
        status, members = self.request("GET", "/v1/team/members", headers={"Authorization": f"Bearer {owner['access_token']}"})
        self.assertEqual(status, 200)
        self.assertEqual(len(members["members"]), 2)

    def test_team_invite_is_hashed_bound_to_member_and_audited(self) -> None:
        status, owner = self.request("POST", "/v1/auth/register", {"email": "invite-owner@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        status, member = self.request("POST", "/v1/auth/register", {"email": "invite-member@example.com", "password": "a-long-test-password"})
        self.assertEqual(status, 201)
        webhook = {"event_id": "invite-team-plan", "account_id": owner["account_id"], "plan": "Team", "status": "active", "expires_at": "2099-01-01T00:00:00Z"}
        raw = json.dumps(webhook).encode("utf-8")
        signature = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
        self.request("POST", "/v1/webhooks/polar", webhook, headers={"X-Bookmark-Intelligence-Signature": f"sha256={signature}"})
        status, invite = self.request("POST", "/v1/team/invites", {"member_email": "invite-member@example.com", "ttl_hours": 24}, headers={"Authorization": f"Bearer {owner['access_token']}"})
        self.assertEqual(status, 201)
        self.assertTrue(invite["invite_token"])
        connection = self.server.billing_service._connect()
        try:
            stored = connection.execute("SELECT token_hash FROM team_invites").fetchone()["token_hash"]
        finally:
            connection.close()
        self.assertNotEqual(stored, invite["invite_token"])
        status, accepted = self.request("POST", "/v1/team/invites/accept", {"invite_token": invite["invite_token"]}, headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(status, 200)
        self.assertEqual(accepted["owner_account_id"], owner["account_id"])
        status, audit = self.request("GET", "/v1/team/audit", headers={"Authorization": f"Bearer {owner['access_token']}"})
        self.assertEqual(status, 200)
        self.assertEqual([event["event_type"] for event in audit["events"][:2]], ["invite_accepted", "invite_created"])
        status, reused = self.request("POST", "/v1/team/invites/accept", {"invite_token": invite["invite_token"]}, headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(status, 400)
        self.assertFalse(reused["ok"])

    def test_email_verification_and_password_reset_revoke_sessions(self) -> None:
        from server.billing_service import BillingService

        service = BillingService(
            Path(self.tempdir.name) / "auth.sqlite3",
            "test-webhook-secret",
            require_email_verification=True,
            expose_action_tokens=True,
        )
        registered = service.register("secure@example.com", "old-password-123")
        self.assertNotIn("access_token", registered)
        with self.assertRaises(PermissionError):
            service.login("secure@example.com", "old-password-123")
        verified = service.verify_email(registered["token"])
        self.assertTrue(verified["email_verified"])
        logged_in = service.login("secure@example.com", "old-password-123")
        reset = service.request_password_reset("secure@example.com")
        self.assertTrue(reset["ok"])
        service.reset_password(reset["token"], "new-password-123")
        with self.assertRaises(PermissionError):
            service.entitlement(registered["account_id"], logged_in["access_token"])
        new_login = service.login("secure@example.com", "new-password-123")
        self.assertTrue(new_login["access_token"])

    def test_smtp_sender_uses_configured_transport(self) -> None:
        from server.billing_service import BillingService

        service = BillingService(
            Path(self.tempdir.name) / "smtp.sqlite3",
            "test-webhook-secret",
            smtp_settings={"host": "smtp.example.test", "port": 587, "username": "mailer", "password": "secret", "from": "mailer@example.test", "starttls": True},
        )
        with patch("server.billing_service.smtplib.SMTP") as smtp_class:
            service._send_email("person@example.test", "Subject", "Body")
        smtp_class.assert_called_once_with("smtp.example.test", 587, timeout=15)
        client = smtp_class.return_value.__enter__.return_value
        client.starttls.assert_called_once_with()
        client.login.assert_called_once_with("mailer", "secret")
        client.send_message.assert_called_once()

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

    def test_polar_checkout_creates_provider_session_and_order_mapping(self) -> None:
        from server.billing_service import BillingService

        service = BillingService(
            Path(self.tempdir.name) / "checkout.sqlite3",
            base64.b64encode(b"polar-secret").decode("ascii"),
            public_base_url="https://billing.example.test",
            polar_access_token="polar-token",
            polar_product_ids={"Solo": "product-solo"},
        )
        registered = service.register("checkout@example.com", "a-long-test-password")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"id": "checkout-123", "url": "https://polar.example/checkout-123"}).encode("utf-8")

        with patch("server.billing_service.urlopen", return_value=FakeResponse()) as open_url:
            result = service.create_polar_checkout(registered["access_token"], "Solo")

        self.assertEqual(result["checkout_id"], "checkout-123")
        self.assertEqual(result["checkout_url"], "https://polar.example/checkout-123")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.polar.sh/v1/checkouts")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["products"], ["product-solo"])
        self.assertEqual(body["metadata"], {"account_id": registered["account_id"], "plan": "Solo"})
        self.assertEqual(service._order("checkout-123")["account_id"], registered["account_id"])


if __name__ == "__main__":
    unittest.main()
