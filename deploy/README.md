# Billing Deployment

The billing service is a separate HTTPS service. GitHub Pages can host the static installation site, but it cannot receive payment webhooks or safely store billing credentials.

## Docker deployment

1. Copy `billing.env.example` to `billing.env` and replace every `replace-with-*` value.
2. Set `PUBLIC_BASE_URL` to the final HTTPS origin, without a trailing slash.
3. Create Polar products for the paid plans and copy their product IDs into the matching variables.
4. In Polar, register the webhook URL `https://billing.example.com/v1/webhooks/polar` and use its Standard Webhooks signing secret as `BOOKMARK_INTELLIGENCE_WEBHOOK_SECRET`.
5. Start the service with `docker compose -f deploy/billing-compose.yml up -d --build` from the repository root.
6. Put an HTTPS reverse proxy in front of `127.0.0.1:8787` and verify `https://billing.example.com/health`.
7. Open `https://billing.example.com/billing` and complete a test checkout.

The billing page creates an account, starts a Polar Checkout Session, redirects to Polar, and returns to the page after checkout. The webhook is the source of truth for Pro entitlement; a browser redirect alone never activates a plan.

## Connect the desktop app

In the user's local `config.toml`:

```toml
[billing]
url = "https://billing.example.com/billing"
```

Restart the Native Messaging host or worker. The extension options page will then enable **Purchase Pro** and open the billing page. If this URL is empty, the button stays disabled and no payment is requested.

## Production gate

Do not expose the service without HTTPS, persistent database backups, secret management, SMTP deliverability, provider refund/cancellation procedures, and a verified live webhook event. The repository contains the runnable checkout path and deployment files; the actual production account, credentials, domain, and hosting project remain operator-owned configuration.
