# Billing Service

This is the minimal self-hostable entitlement service for Bookmark Intelligence. It provides:

- account registration and password login
- bearer access tokens for the local agent
- Free/Solo/Duo/Team/Enterprise entitlement responses
- idempotent entitlement updates from verified Polar/Toss payment events

Run locally:

```powershell
$env:BOOKMARK_INTELLIGENCE_WEBHOOK_SECRET = "base64-encoded-Polar-webhook-secret"
.venv\Scripts\python.exe .\server\billing_service.py --database .\billing.sqlite3
```

For Polar, use the base64-encoded signing secret shown by Polar. `TOSS_SECRET_KEY` is a separate environment variable used for server-side payment re-query:

```powershell
$env:TOSS_SECRET_KEY = "test_sk_..."
```

Register and log in:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/auth/register -Method Post -ContentType application/json -Body (@{email="you@example.com";password="at-least-12-characters"} | ConvertTo-Json)
```

The returned bearer token is configured for the local agent through `[entitlements]`.

Payment flow:

1. The authenticated client creates an order with `POST /v1/orders` and receives an order mapping. The mapping keeps the payment provider's `orderId` tied to the Bookmark Intelligence account and selected plan.
2. Polar events are accepted at `POST /v1/webhooks/polar` only after Standard Webhooks signature and timestamp verification. The Polar payload must carry `account_id` and `plan` in its metadata; the adapter normalizes subscription state.
3. Toss `PAYMENT_STATUS_CHANGED` events are accepted at `POST /v1/webhooks/toss` only when the order is known and the server re-queries Toss with `TOSS_SECRET_KEY`. A raw Toss webhook is never treated as proof of payment.

The generic HMAC endpoint remains available at other `/v1/webhooks/<provider>` paths for already-verified self-hosted adapters and local tests. It is not a substitute for provider-specific verification.

The service applies a small per-process, per-IP rate limit to API, authentication, entitlement, and webhook requests and rejects JSON bodies larger than 1 MiB. A public deployment still needs an HTTPS reverse proxy, distributed rate limiting, a managed database backup, email verification, password reset, and a secrets manager. The included service is a reference implementation, not a complete hosted payment product.

The service does not store Vault notes, raw webpages, transcripts, or AI API keys.
