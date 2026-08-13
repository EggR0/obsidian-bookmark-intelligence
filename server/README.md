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

Polar checkout configuration:

```powershell
$env:POLAR_ACCESS_TOKEN = "polar_organization_access_token"
$env:POLAR_SOLO_PRODUCT_ID = "polar_solo_product_uuid"
$env:POLAR_DUO_PRODUCT_ID = "polar_duo_product_uuid"
$env:POLAR_TEAM_PRODUCT_ID = "polar_team_product_uuid"
$env:PUBLIC_BASE_URL = "https://billing.example.com"
```

The billing page is served at `/billing`. It registers or signs in an account, calls `POST /v1/checkouts`, and redirects the customer to the Polar Checkout Session URL. Polar metadata carries the account and plan into the resulting subscription; the verified Standard Webhook then activates the matching entitlement. Keep `POLAR_ACCESS_TOKEN` on the server only.

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

The login response contains `account_id` and a bearer `access_token`. Configure the endpoint, account ID, and token environment-variable name from the extension settings page, then set the token in the same user/session environment that starts the worker:

```powershell
$login = Invoke-RestMethod http://127.0.0.1:8787/v1/auth/login -Method Post -ContentType application/json -Body (@{email="you@example.com";password="at-least-12-characters"} | ConvertTo-Json)
$env:BOOKMARK_INTELLIGENCE_ACCESS_TOKEN = $login.access_token
bookmark-agent --config .\config.toml refresh-entitlement
```

The token is intentionally not written to the Vault, SQLite, extension storage, or the app settings file. Start the worker from the same process/session after setting it, or configure the environment variable through the operating system's user-level secret management. Do not place the token in a committed script or public repository.

Payment flow:

1. The authenticated client calls `POST /v1/checkouts` with a paid plan. The server creates a Polar Checkout Session with the server-only Polar access token and records the checkout ID to account and plan mapping.
2. The customer completes payment at the returned Polar checkout URL. Polar events are accepted at `POST /v1/webhooks/polar` only after Standard Webhooks signature and timestamp verification. The Polar payload must carry `account_id` and `plan` in its metadata; the adapter normalizes subscription state.
3. Toss `PAYMENT_STATUS_CHANGED` events are accepted at `POST /v1/webhooks/toss` only when the order is known and the server re-queries Toss with `TOSS_SECRET_KEY`. A raw Toss webhook is never treated as proof of payment.

`POST /v1/orders` remains available for provider-specific order mappings such as Toss. Polar product IDs and payment credentials are empty by default, so checkout remains unavailable until the operator configures a real Polar organization.

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

Duo supports 2 total seats, Team supports 5 total seats, and Enterprise has no enforced seat cap in this reference service. A member uses their own login token, while the owner's subscription and shared credits are charged. `POST /v1/team/members/remove` removes a member. The included service also provides email verification, password-reset tokens, expiring email invites, and owner-visible audit events. A production deployment still needs a real SMTP/transactional-email configuration, HTTPS, secret management, abuse monitoring, and organization-specific administration policies.

The reference service also supports a secure invite handoff. The owner creates an invite by email; when SMTP is configured the service sends the invite message, otherwise the response contains the one-time token for a local administrator to deliver:

```powershell
$invite = Invoke-RestMethod http://127.0.0.1:8787/v1/team/invites -Method Post -Headers @{Authorization="Bearer <owner-token>"} -ContentType application/json -Body (@{member_email="member@example.com";ttl_hours=72} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8787/v1/team/invites/accept -Method Post -Headers @{Authorization="Bearer <member-token>"} -ContentType application/json -Body (@{invite_token=$invite.invite_token} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8787/v1/team/audit -Headers @{Authorization="Bearer <owner-token>"}
```

Only the token hash is stored, it expires, it is bound to the invited account, and it cannot be accepted twice. Team invite creation, acceptance, and removal are recorded in the owner-visible audit feed. Set `REQUIRE_EMAIL_VERIFICATION=1` to require verified email addresses before login; configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `SMTP_STARTTLS` for delivery. Password-reset action tokens are never returned by default; `EXPOSE_AUTH_ACTION_TOKENS=1` is intended only for controlled local development.

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

The service applies a small per-process, per-IP rate limit to API, authentication, entitlement, and webhook requests and rejects JSON bodies larger than 1 MiB. A public deployment still needs an HTTPS reverse proxy, distributed rate limiting, a managed database backup, a secrets manager, abuse monitoring, and production email deliverability controls. The Polar checkout path is implemented, but production operation still requires those controls plus refund, cancellation, and provider webhook procedures.

The service does not store Vault notes, raw webpages, transcripts, or AI API keys.
