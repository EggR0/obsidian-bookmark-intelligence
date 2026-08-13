# Billing Service

This is the minimal self-hostable entitlement service for Bookmark Intelligence. It provides:

- account registration and password login
- bearer access tokens for the local agent
- Free/Solo/Duo/Team/Enterprise entitlement responses
- HMAC-signed, idempotent normalized webhook ingestion for Polar/Toss adapters

Run locally:

```powershell
$env:BOOKMARK_INTELLIGENCE_WEBHOOK_SECRET = "replace-with-a-long-random-secret"
.venv\Scripts\python.exe .\server\billing_service.py --database .\billing.sqlite3
```

Register and log in:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/auth/register -Method Post -ContentType application/json -Body (@{email="you@example.com";password="at-least-12-characters"} | ConvertTo-Json)
```

The returned bearer token is configured for the local agent through `[entitlements]`. The public deployment must use HTTPS, a managed database backup, rate limiting, email verification, password reset, and a secrets manager. Provider-specific Polar/Toss webhook handlers must normalize their verified payloads to `event_id`, `account_id`, `plan`, `status`, `expires_at`, and optional `hosted_credits` before calling the generic webhook endpoint.

The service does not store Vault notes, raw webpages, transcripts, or AI API keys.
