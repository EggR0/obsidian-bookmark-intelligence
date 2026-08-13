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

Optional account email security can be enabled for a public deployment:

```powershell
$env:REQUIRE_EMAIL_VERIFICATION = "1"
$env:SMTP_HOST = "smtp.example.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "mailer@example.com"
$env:SMTP_PASSWORD = "read-from-a-secret-manager"
$env:SMTP_FROM = "Bookmark Intelligence <mailer@example.com>"
$env:SMTP_STARTTLS = "1"
```

With verification required, registration creates a one-time email-verification token and login is denied until `POST /v1/auth/verify-email` consumes it. `POST /v1/auth/request-password-reset` always returns a generic response to avoid account enumeration; the service sends a reset token when SMTP is configured. `POST /v1/auth/reset-password` consumes that token, changes the password, and revokes all existing access tokens. `EXPOSE_AUTH_ACTION_TOKENS=1` is available only for controlled local development and is disabled by default.

Register and log in:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/auth/register -Method Post -ContentType application/json -Body (@{email="you@example.com";password="at-least-12-characters"} | ConvertTo-Json)
```

The returned bearer token is configured for the local agent through `[entitlements]`.

Payment flow:

1. The authenticated client creates an order with `POST /v1/orders` and receives an order mapping. The mapping keeps the payment provider's `orderId` tied to the Bookmark Intelligence account and selected plan.
2. Polar events are accepted at `POST /v1/webhooks/polar` only after Standard Webhooks signature and timestamp verification. The Polar payload must carry `account_id` and `plan` in its metadata; the adapter normalizes subscription state.
3. Toss `PAYMENT_STATUS_CHANGED` events are accepted at `POST /v1/webhooks/toss` only when the order is known and the server re-queries Toss with `TOSS_SECRET_KEY`. A raw Toss webhook is never treated as proof of payment.

Hosted AI gateways can reserve usage with `POST /v1/usage/consume` using the user's bearer token and either a JSON `request_id` or `Idempotency-Key` header:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/usage/consume -Method Post -Headers @{Authorization="Bearer <token>";"Idempotency-Key"="summary-123"} -ContentType application/json -Body (@{units=1} | ConvertTo-Json)
```

The operation requires an active paid plan, decrements `hosted_credits` atomically, and returns HTTP 402 when the balance is insufficient. Repeating the same request key does not charge twice. Local Ollama and user-owned provider API keys do not use this endpoint.

Team plans share the owner's entitlement and hosted-credit balance. An owner can link an already registered account with `POST /v1/team/members`:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/v1/team/members -Method Post -Headers @{Authorization="Bearer <owner-token>"} -ContentType application/json -Body (@{member_account_id="acct_member"} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8787/v1/team/members -Headers @{Authorization="Bearer <owner-or-member-token>"}
```

Duo supports 2 total seats, Team supports 5 total seats, and Enterprise has no enforced seat cap in this reference service. A member uses their own login token, while the owner's subscription and shared credits are charged. `POST /v1/team/members/remove` removes a member. Production deployments should add email invitations, verification, audit logs, and organization administration before treating this as a complete enterprise identity system.

The reference service also supports a secure invite handoff for already registered accounts. The owner creates an invite by email; the response contains the one-time token, which an external mailer or administrator can deliver to that user:

```powershell
$invite = Invoke-RestMethod http://127.0.0.1:8787/v1/team/invites -Method Post -Headers @{Authorization="Bearer <owner-token>"} -ContentType application/json -Body (@{member_email="member@example.com";ttl_hours=72} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8787/v1/team/invites/accept -Method Post -Headers @{Authorization="Bearer <member-token>"} -ContentType application/json -Body (@{invite_token=$invite.invite_token} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8787/v1/team/audit -Headers @{Authorization="Bearer <owner-token>"}
```

Only the token hash is stored, it expires, it is bound to the invited account, and it cannot be accepted twice. The included service does not send email itself. Team invite creation, acceptance, and removal are recorded in the owner-visible audit feed.

Run the optional hosted gateway separately:

```powershell
$env:BILLING_ENDPOINT = "https://billing.example.com"
$env:HOSTED_AI_BASE_URL = "https://api.openai.com/v1"
$env:HOSTED_AI_API_KEY = "server-side-upstream-key"
$env:HOSTED_AI_MODEL = "gpt-4o-mini"
.venv\Scripts\python.exe .\server\hosted_gateway.py
```

The gateway accepts `POST /v1/summarize` with `account_id`, `request_id`, `prompt`, `source_text`, and optional `model`. It performs the billing entitlement check before the upstream call, then charges one credit only after a non-empty upstream summary is returned. Deploy it behind HTTPS and keep the upstream key out of the repository and client configuration.

The generic HMAC endpoint remains available at other `/v1/webhooks/<provider>` paths for already-verified self-hosted adapters and local tests. It is not a substitute for provider-specific verification.

The service applies a small per-process, per-IP rate limit to API, authentication, entitlement, and webhook requests and rejects JSON bodies larger than 1 MiB. A public deployment still needs an HTTPS reverse proxy, distributed rate limiting, a managed database backup, a secrets manager, abuse monitoring, and production email deliverability controls. The included service is a reference implementation, not a complete hosted payment product.

The service does not store Vault notes, raw webpages, transcripts, or AI API keys.
