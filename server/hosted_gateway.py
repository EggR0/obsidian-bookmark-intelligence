from __future__ import annotations

from dataclasses import dataclass
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from typing import Any
from urllib.parse import urlparse

import requests


class GatewayRequestError(ValueError):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GatewaySettings:
    billing_endpoint: str
    upstream_base_url: str
    upstream_api_key: str
    default_model: str
    timeout_seconds: int = 120
    max_source_chars: int = 12000


def _bearer(value: str | None) -> str:
    token = (value or "").removeprefix("Bearer ").strip()
    if not token:
        raise GatewayRequestError("Bearer access token is required", HTTPStatus.UNAUTHORIZED)
    return token


def _json_response(response: requests.Response, message: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        detail = payload.get("error") if isinstance(payload, dict) else None
        raise GatewayRequestError(detail or message, response.status_code)
    return payload if isinstance(payload, dict) else {}


def summarize_hosted(payload: dict[str, Any], authorization: str | None, settings: GatewaySettings) -> dict[str, Any]:
    token = _bearer(authorization)
    account_id = str(payload.get("account_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    source_text = str(payload.get("source_text") or "")
    title = str(payload.get("title") or "")
    url = str(payload.get("url") or "")
    model = str(payload.get("model") or settings.default_model).strip()
    if not account_id or not request_id or not prompt:
        raise GatewayRequestError("account_id, request_id, and prompt are required")
    if not source_text:
        raise GatewayRequestError("source_text is required")
    if len(source_text) > settings.max_source_chars:
        raise GatewayRequestError(f"source_text exceeds {settings.max_source_chars} characters")
    if not settings.upstream_api_key:
        raise GatewayRequestError("Hosted upstream API key is not configured", HTTPStatus.SERVICE_UNAVAILABLE)

    auth_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    entitlement_response = requests.get(
        f"{settings.billing_endpoint.rstrip('/')}/v1/entitlements/{account_id}",
        headers=auth_headers,
        timeout=settings.timeout_seconds,
    )
    entitlement = _json_response(entitlement_response, "Billing entitlement lookup failed")
    if entitlement.get("plan") == "Free" or int(entitlement.get("hosted_credits", 0)) < 1:
        raise GatewayRequestError("An active hosted-AI credit balance is required", HTTPStatus.PAYMENT_REQUIRED)

    upstream_response = requests.post(
        f"{settings.upstream_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.upstream_api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=settings.timeout_seconds,
    )
    upstream = _json_response(upstream_response, "Hosted AI upstream request failed")
    summary = (((upstream.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not summary:
        raise GatewayRequestError("Hosted AI upstream returned an empty summary", HTTPStatus.BAD_GATEWAY)

    usage_response = requests.post(
        f"{settings.billing_endpoint.rstrip('/')}/v1/usage/consume",
        headers={**auth_headers, "Content-Type": "application/json", "Idempotency-Key": request_id},
        json={"units": 1, "request_id": request_id},
        timeout=settings.timeout_seconds,
    )
    usage = _json_response(usage_response, "Hosted credit consumption failed")
    return {"ok": True, "summary": summary, "model": model, "provider": "hosted", "usage": usage}


class GatewayHandler(BaseHTTPRequestHandler):
    settings: GatewaySettings

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/v1/summarize":
            self._write(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_048_576:
                raise GatewayRequestError("Request body is too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = summarize_hosted(payload, self.headers.get("Authorization"), self.settings)
            self._write(HTTPStatus.OK, result)
        except GatewayRequestError as error:
            self._write(error.status, {"ok": False, "error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
        except requests.RequestException as error:
            self._write(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": f"Gateway network error: {error}"})

    def log_message(self, *_args: object) -> None:
        return


def create_server(host: str, port: int, settings: GatewaySettings) -> ThreadingHTTPServer:
    class Handler(GatewayHandler):
        pass

    Handler.settings = settings
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Bookmark Intelligence hosted AI gateway")
    parser.add_argument("--host", default=os.environ.get("HOSTED_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HOSTED_GATEWAY_PORT", "8788")))
    parser.add_argument("--billing-endpoint", default=os.environ.get("BILLING_ENDPOINT", ""))
    parser.add_argument("--upstream-base-url", default=os.environ.get("HOSTED_AI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--upstream-api-key", default=os.environ.get("HOSTED_AI_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("HOSTED_AI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    if not args.billing_endpoint or not args.upstream_api_key:
        parser.error("--billing-endpoint/BILLING_ENDPOINT and --upstream-api-key/HOSTED_AI_API_KEY are required")
    server = create_server(args.host, args.port, GatewaySettings(args.billing_endpoint, args.upstream_base_url, args.upstream_api_key, args.model))
    print(f"Hosted AI gateway listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
