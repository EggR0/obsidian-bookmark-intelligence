from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

import requests

from .config import AppConfig
from .vault_state import state_dir


ENTITLEMENT_CACHE = "entitlement.json"
PRO_FEATURES = {"bulk_analysis", "duplicate_report", "backup", "restore"}


def entitlement_path(config: AppConfig) -> Path:
    return state_dir(config) / ENTITLEMENT_CACHE


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def read_entitlement(config: AppConfig) -> dict:
    path = entitlement_path(config)
    if not path.exists():
        return {"status": "inactive", "features": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "inactive", "features": []}
    if not isinstance(payload, dict):
        return {"status": "inactive", "features": []}
    return payload


def _active(payload: dict) -> bool:
    if payload.get("status") not in {"active", "trialing"}:
        return False
    expires_at = _parse_time(payload.get("expires_at"))
    return expires_at is None or expires_at > datetime.now(UTC)


def has_feature(config: AppConfig, feature: str) -> bool:
    if config.features.pro_enabled:
        return True
    if feature not in PRO_FEATURES:
        return False
    payload = read_entitlement(config)
    return _active(payload) and feature in set(payload.get("features") or [])


def current_plan(config: AppConfig) -> str:
    if config.features.pro_enabled:
        return "Pro (development override)"
    payload = read_entitlement(config)
    return str(payload.get("plan") or "Free") if _active(payload) else "Free"


def refresh_entitlement(config: AppConfig) -> dict:
    endpoint = config.entitlements.endpoint
    account_id = config.entitlements.account_id
    token_name = config.entitlements.access_token_env
    if not endpoint or not account_id or not token_name:
        raise ValueError("Entitlement endpoint, account_id, and access_token_env must be configured")
    token = os.environ.get(token_name)
    if not token:
        raise ValueError(f"Entitlement access token environment variable is not set: {token_name}")

    response = requests.get(
        f"{endpoint}/v1/entitlements/{account_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=config.entitlements.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("features", []), list):
        raise ValueError("Entitlement server returned an invalid response")
    payload = {
        "account_id": account_id,
        "plan": str(payload.get("plan") or "Free"),
        "status": str(payload.get("status") or "inactive"),
        "features": [str(feature) for feature in payload.get("features", [])],
        "expires_at": payload.get("expires_at"),
        "refreshed_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    entitlement_path(config).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
