from __future__ import annotations

from datetime import UTC, datetime
from contextlib import contextmanager
import hashlib
import hmac
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import base64

try:
    from .provider_adapters import normalize_polar, normalize_toss, verify_standard_webhook
except ImportError:  # pragma: no cover - supports `python server/billing_service.py`
    from provider_adapters import normalize_polar, normalize_toss, verify_standard_webhook


PLAN_FEATURES = {
    "Free": [],
    "Solo": ["bulk_analysis", "duplicate_report", "backup", "restore"],
    "Duo": ["bulk_analysis", "duplicate_report", "backup", "restore"],
    "Team": ["bulk_analysis", "duplicate_report", "backup", "restore"],
    "Enterprise": ["bulk_analysis", "duplicate_report", "backup", "restore"],
}
PLAN_CREDITS = {"Free": 0, "Solo": 300, "Duo": 500, "Team": 800, "Enterprise": 0}
MAX_REQUEST_BYTES = 1_048_576


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _active(status: str, expires_at: str | None) -> bool:
    if status not in {"active", "trialing"}:
        return False
    expiry = _parse_expiry(expires_at)
    return expiry is None or expiry > datetime.now(UTC)


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str], list[float]] = {}

    def allow(self, key: str, bucket: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        identifier = (key, bucket)
        with self._lock:
            recent = [value for value in self._windows.get(identifier, []) if now - value < window_seconds]
            if len(recent) >= limit:
                self._windows[identifier] = recent
                return False
            recent.append(now)
            self._windows[identifier] = recent
            return True


class BillingService:
    def __init__(self, database_path: Path, webhook_secret: str, toss_secret_key: str = ""):
        self.database_path = database_path
        self.webhook_secret = webhook_secret
        self.toss_secret_key = toss_secret_key
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _db(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._db() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                  account_id TEXT PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  password_salt BLOB NOT NULL,
                  password_hash BLOB NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_tokens (
                  token_hash TEXT PRIMARY KEY,
                  account_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                  account_id TEXT PRIMARY KEY,
                  plan TEXT NOT NULL,
                  status TEXT NOT NULL,
                  expires_at TEXT,
                  hosted_credits INTEGER NOT NULL DEFAULT 0,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                CREATE TABLE IF NOT EXISTS webhook_events (
                  provider TEXT NOT NULL,
                  event_id TEXT NOT NULL,
                  received_at TEXT NOT NULL,
                  PRIMARY KEY(provider, event_id)
                );
                CREATE TABLE IF NOT EXISTS payment_orders (
                  order_id TEXT PRIMARY KEY,
                  account_id TEXT NOT NULL,
                  plan TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                );
                """
            )

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)

    @staticmethod
    def _validate_credentials(email: str, password: str) -> tuple[str, str]:
        normalized = email.strip().lower()
        if "@" not in normalized or len(normalized) > 320:
            raise ValueError("A valid email is required")
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        return normalized, password

    def register(self, email: str, password: str) -> dict:
        email, password = self._validate_credentials(email, password)
        account_id = f"acct_{secrets.token_urlsafe(12)}"
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(password, salt)
        try:
            with self._db() as connection:
                connection.execute(
                    "INSERT INTO accounts (account_id, email, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (account_id, email, salt, password_hash, utc_now()),
                )
                connection.execute(
                    "INSERT INTO subscriptions (account_id, plan, status, hosted_credits, updated_at) VALUES (?, 'Free', 'active', 0, ?)",
                    (account_id, utc_now()),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("An account with this email already exists") from error
        return self._issue_token(account_id)

    def login(self, email: str, password: str) -> dict:
        email, password = self._validate_credentials(email, password)
        with self._db() as connection:
            account = connection.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        if not account or not hmac.compare_digest(self._password_hash(password, account["password_salt"]), account["password_hash"]):
            raise ValueError("Invalid email or password")
        return self._issue_token(account["account_id"])

    def _issue_token(self, account_id: str) -> dict:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._db() as connection:
            connection.execute(
                "INSERT INTO access_tokens (token_hash, account_id, created_at) VALUES (?, ?, ?)",
                (token_hash, account_id, utc_now()),
            )
        return {"account_id": account_id, "access_token": token, "token_type": "Bearer"}

    def _account_for_token(self, token: str | None) -> str | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._db() as connection:
            row = connection.execute("SELECT account_id FROM access_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        return row["account_id"] if row else None

    def create_payment_order(self, token: str | None, order_id: str, plan: str) -> dict:
        account_id = self._account_for_token(token)
        if not account_id:
            raise PermissionError("Invalid access token")
        order_id = order_id.strip()
        if not order_id or plan not in PLAN_FEATURES or plan == "Free":
            raise ValueError("A non-Free plan and order_id are required")
        with self._db() as connection:
            connection.execute(
                "INSERT INTO payment_orders (order_id, account_id, plan, created_at) VALUES (?, ?, ?, ?)",
                (order_id, account_id, plan, utc_now()),
            )
        return {"order_id": order_id, "account_id": account_id, "plan": plan}

    def _order(self, order_id: str) -> sqlite3.Row | None:
        with self._db() as connection:
            return connection.execute("SELECT * FROM payment_orders WHERE order_id = ?", (order_id,)).fetchone()

    def _verify_toss_payment(self, payment_key: str, order_id: str, expected_status: str) -> None:
        if not self.toss_secret_key:
            raise PermissionError("Toss payment verification is not configured")
        credentials = base64.b64encode(f"{self.toss_secret_key}:".encode("utf-8")).decode("ascii")
        request = Request(
            f"https://api.tosspayments.com/v1/payments/{payment_key}",
            headers={"Authorization": f"Basic {credentials}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                verified = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise PermissionError("Toss payment could not be verified") from error
        if verified.get("orderId") != order_id or verified.get("status") != expected_status:
            raise PermissionError("Toss payment verification did not match the webhook")

    def entitlement(self, account_id: str, token: str | None) -> dict:
        if self._account_for_token(token) != account_id:
            raise PermissionError("Invalid access token")
        with self._db() as connection:
            row = connection.execute("SELECT * FROM subscriptions WHERE account_id = ?", (account_id,)).fetchone()
        if not row or not _active(row["status"], row["expires_at"]):
            return {"account_id": account_id, "plan": "Free", "status": "inactive", "features": [], "hosted_credits": 0, "expires_at": None}
        plan = row["plan"] if row["plan"] in PLAN_FEATURES else "Free"
        return {
            "account_id": account_id,
            "plan": plan,
            "status": row["status"],
            "features": PLAN_FEATURES[plan],
            "hosted_credits": row["hosted_credits"],
            "expires_at": row["expires_at"],
        }

    def apply_webhook(self, provider: str, payload: dict, signature: str | None, raw_body: bytes) -> dict:
        if not self.webhook_secret:
            raise PermissionError("Webhook secret is not configured")
        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        supplied = (signature or "").removeprefix("sha256=")
        if not hmac.compare_digest(expected, supplied):
            raise PermissionError("Invalid webhook signature")
        event_id = str(payload.get("event_id") or "").strip()
        account_id = str(payload.get("account_id") or "").strip()
        if not event_id or not account_id:
            raise ValueError("event_id and account_id are required")
        plan = str(payload.get("plan") or "Free")
        status = str(payload.get("status") or "inactive")
        expires_at = payload.get("expires_at")
        if plan not in PLAN_FEATURES or (expires_at and _parse_expiry(expires_at) is None):
            raise ValueError("Invalid plan or expires_at")
        credits = int(payload.get("hosted_credits", PLAN_CREDITS[plan]))
        with self._db() as connection:
            existing = connection.execute("SELECT 1 FROM webhook_events WHERE provider = ? AND event_id = ?", (provider, event_id)).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "event_id": event_id}
            account = connection.execute("SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
            if not account:
                raise ValueError("Unknown account_id")
            connection.execute(
                "INSERT INTO subscriptions (account_id, plan, status, expires_at, hosted_credits, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET plan=excluded.plan, status=excluded.status, expires_at=excluded.expires_at, hosted_credits=excluded.hosted_credits, updated_at=excluded.updated_at",
                (account_id, plan, status, expires_at, credits, utc_now()),
            )
            connection.execute("INSERT INTO webhook_events (provider, event_id, received_at) VALUES (?, ?, ?)", (provider, event_id, utc_now()))
        return {"ok": True, "duplicate": False, "event_id": event_id, "account_id": account_id}

    def apply_polar_webhook(self, payload: dict, raw_body: bytes, headers: dict[str, str]) -> dict:
        # Keep the normalized HMAC endpoint usable for local adapter tests and self-hosted integrations.
        if payload.get("event_id") and payload.get("account_id"):
            return self.apply_webhook("polar", payload, headers.get("x-bookmark-intelligence-signature"), raw_body)
        verify_standard_webhook(self.webhook_secret, raw_body, headers)
        normalized = normalize_polar(payload, headers.get("webhook-id"))
        return self._apply_normalized_webhook("polar", normalized)

    def apply_toss_webhook(self, payload: dict) -> dict:
        preliminary = normalize_toss(payload)
        order = self._order(preliminary["order_id"])
        if not order:
            raise ValueError("Unknown Toss order_id")
        if not preliminary["payment_key"]:
            raise ValueError("Toss paymentKey is required")
        self._verify_toss_payment(preliminary["payment_key"], preliminary["order_id"], preliminary["status"])
        normalized = normalize_toss(payload, order["account_id"], order["plan"])
        return self._apply_normalized_webhook("toss", normalized)

    def _apply_normalized_webhook(self, provider: str, payload: dict) -> dict:
        return self._apply_subscription(provider, payload)

    def _apply_subscription(self, provider: str, payload: dict) -> dict:
        event_id = str(payload.get("event_id") or "").strip()
        account_id = str(payload.get("account_id") or "").strip()
        if not event_id or not account_id:
            raise ValueError("event_id and account_id are required")
        plan = str(payload.get("plan") or "Free")
        status = str(payload.get("status") or "inactive")
        expires_at = payload.get("expires_at")
        if plan not in PLAN_FEATURES or (expires_at and _parse_expiry(expires_at) is None):
            raise ValueError("Invalid plan or expires_at")
        credits = int(payload.get("hosted_credits", PLAN_CREDITS[plan]))
        with self._db() as connection:
            existing = connection.execute("SELECT 1 FROM webhook_events WHERE provider = ? AND event_id = ?", (provider, event_id)).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "event_id": event_id}
            if not connection.execute("SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)).fetchone():
                raise ValueError("Unknown account_id")
            connection.execute(
                "INSERT INTO subscriptions (account_id, plan, status, expires_at, hosted_credits, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET plan=excluded.plan, status=excluded.status, expires_at=excluded.expires_at, hosted_credits=excluded.hosted_credits, updated_at=excluded.updated_at",
                (account_id, plan, status, expires_at, credits, utc_now()),
            )
            connection.execute("INSERT INTO webhook_events (provider, event_id, received_at) VALUES (?, ?, ?)", (provider, event_id, utc_now()))
        return {"ok": True, "duplicate": False, "event_id": event_id, "account_id": account_id}


class BillingRequestHandler(BaseHTTPRequestHandler):
    service: BillingService
    rate_limiter: RateLimiter

    def _write(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> tuple[dict, bytes]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_REQUEST_BYTES:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8") or "{}"), raw

    def _allow_request(self, bucket: str, limit: int) -> bool:
        address = self.client_address[0] if self.client_address else "unknown"
        if self.rate_limiter.allow(address, bucket, limit):
            return True
        self._write(HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": "Too many requests"})
        return False

    def _bearer(self) -> str | None:
        value = self.headers.get("Authorization", "")
        return value.removeprefix("Bearer ").strip() or None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write(HTTPStatus.OK, {"ok": True})
            return
        prefix = "/v1/entitlements/"
        if parsed.path.startswith(prefix):
            if not self._allow_request("entitlement", 120):
                return
            account_id = parsed.path.removeprefix(prefix).strip("/")
            try:
                self._write(HTTPStatus.OK, self.service.entitlement(account_id, self._bearer()))
            except PermissionError as error:
                self._write(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(error)})
            return
        self._write(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            bucket = "webhook" if self.path.startswith("/v1/webhooks/") else "auth" if self.path.startswith("/v1/auth/") else "api"
            limit = 120 if bucket == "webhook" else 20 if bucket == "auth" else 60
            if not self._allow_request(bucket, limit):
                return
            payload, raw_body = self._body()
            if self.path == "/v1/auth/register":
                result = self.service.register(str(payload.get("email", "")), str(payload.get("password", "")))
                self._write(HTTPStatus.CREATED, result)
                return
            if self.path == "/v1/auth/login":
                result = self.service.login(str(payload.get("email", "")), str(payload.get("password", "")))
                self._write(HTTPStatus.OK, result)
                return
            if self.path == "/v1/orders":
                result = self.service.create_payment_order(self._bearer(), str(payload.get("order_id", "")), str(payload.get("plan", "")))
                self._write(HTTPStatus.CREATED, result)
                return
            if self.path == "/v1/webhooks/polar":
                result = self.service.apply_polar_webhook(payload, raw_body, {key.lower(): value for key, value in self.headers.items()})
                self._write(HTTPStatus.OK, result)
                return
            if self.path == "/v1/webhooks/toss":
                if self.headers.get("X-Bookmark-Intelligence-Signature"):
                    result = self.service.apply_webhook("toss", payload, self.headers.get("X-Bookmark-Intelligence-Signature"), raw_body)
                    self._write(HTTPStatus.OK, result)
                    return
                result = self.service.apply_toss_webhook(payload)
                self._write(HTTPStatus.OK, result)
                return
            if self.path.startswith("/v1/webhooks/"):
                provider = self.path.removeprefix("/v1/webhooks/").strip("/")
                result = self.service.apply_webhook(provider, payload, self.headers.get("X-Bookmark-Intelligence-Signature"), raw_body)
                self._write(HTTPStatus.OK, result)
                return
            self._write(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
        except PermissionError as error:
            self._write(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
        except Exception as error:
            self._write(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(error)})

    def log_message(self, *_args: object) -> None:
        return


def create_server(host: str, port: int, database_path: Path, webhook_secret: str, toss_secret_key: str = "") -> ThreadingHTTPServer:
    service = BillingService(database_path, webhook_secret, toss_secret_key)

    class Handler(BillingRequestHandler):
        pass

    Handler.service = service
    Handler.rate_limiter = RateLimiter()
    server = ThreadingHTTPServer((host, port), Handler)
    server.billing_service = service  # type: ignore[attr-defined]
    return server


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Bookmark Intelligence billing service")
    parser.add_argument("--host", default=os.environ.get("BILLING_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BILLING_PORT", "8787")))
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("BILLING_DATABASE", "billing.sqlite3")))
    parser.add_argument("--webhook-secret", default=os.environ.get("BOOKMARK_INTELLIGENCE_WEBHOOK_SECRET", ""))
    parser.add_argument("--toss-secret-key", default=os.environ.get("TOSS_SECRET_KEY", ""))
    args = parser.parse_args()
    if not args.webhook_secret:
        parser.error("--webhook-secret or BOOKMARK_INTELLIGENCE_WEBHOOK_SECRET is required")
    server = create_server(args.host, args.port, args.database, args.webhook_secret, args.toss_secret_key)
    print(f"Billing service listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
