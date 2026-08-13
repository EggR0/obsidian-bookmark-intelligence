from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import UTC, datetime
import hashlib
import hmac
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")
    value = _text(value)
    if value.endswith("Z"):
        return value
    return value


def verify_standard_webhook(secret: str, body: bytes, headers: dict[str, str], tolerance_seconds: int = 300) -> None:
    """Verify the Standard Webhooks envelope used by Polar."""
    webhook_id = _text(headers.get("webhook-id"))
    timestamp = _text(headers.get("webhook-timestamp"))
    supplied = _text(headers.get("webhook-signature"))
    if not webhook_id or not timestamp or not supplied:
        raise PermissionError("Polar webhook headers are incomplete")
    try:
        timestamp_number = int(timestamp)
    except ValueError as error:
        raise PermissionError("Invalid Polar webhook timestamp") from error
    if abs(datetime.now(UTC).timestamp() - timestamp_number) > tolerance_seconds:
        raise PermissionError("Polar webhook timestamp is outside the allowed window")
    try:
        encoded_secret = secret.removeprefix("whsec_")
        decoded_secret = b64decode(encoded_secret + "=" * (-len(encoded_secret) % 4), validate=True)
    except Exception as error:
        raise PermissionError("Polar webhook secret must be base64 encoded") from error
    signed = f"{webhook_id}.{timestamp}.".encode("utf-8") + body
    expected = b64encode(hmac.new(decoded_secret, signed, hashlib.sha256).digest()).decode("ascii")
    valid = any(
        hmac.compare_digest(item.removeprefix("v1,"), expected)
        for item in supplied.split(" ")
    )
    if not valid:
        raise PermissionError("Invalid Polar webhook signature")


def normalize_polar(payload: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    event_type = _text(payload.get("type"))
    account_id = _text(metadata.get("account_id") or data.get("account_id"))
    subscription_id = _text(data.get("id"))
    resolved_event_id = _text(event_id or payload.get("id")) or f"{event_type}:{subscription_id}:{payload.get('timestamp', '')}"
    plan = _text(metadata.get("plan") or data.get("plan") or data.get("product_name")) or "Free"
    status = _text(data.get("status")) or ("active" if event_type in {"subscription.created", "subscription.active"} else "inactive")
    if event_type in {"subscription.canceled", "subscription.revoked", "subscription.past_due"}:
        status = "inactive"
    expires_at = _iso(data.get("current_period_end") or data.get("ends_at"))
    return {
        "event_id": resolved_event_id,
        "account_id": account_id,
        "plan": plan,
        "status": status,
        "expires_at": expires_at,
    }


def normalize_toss(payload: dict[str, Any], account_id: str | None = None, plan: str | None = None) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    event_type = _text(payload.get("eventType"))
    order_id = _text(data.get("orderId") or payload.get("orderId"))
    payment_key = _text(data.get("paymentKey") or payload.get("paymentKey"))
    resolved_account = _text(account_id or data.get("accountId"))
    resolved_plan = _text(plan or data.get("plan")) or "Free"
    status = _text(data.get("status") or payload.get("status"))
    active = status in {"DONE", "WAITING_FOR_DEPOSIT"}
    return {
        "event_id": f"{event_type}:{payment_key or order_id}:{payload.get('createdAt', '')}",
        "account_id": resolved_account,
        "plan": resolved_plan,
        "status": "active" if active else "inactive",
        "expires_at": None,
        "order_id": order_id,
        "payment_key": payment_key,
    }
