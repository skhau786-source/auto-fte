# Payment Integration — 🟢 COMPLETE (implementation) / Live Stripe: NOT VERIFIED

## What exists now

`backend-fte/app/subscriptions/` is a full Stripe billing integration:
Stripe SDK calls isolated behind `StripeClient`, a `SubscriptionService`
that creates Checkout Sessions and Billing Portal sessions, cancels a
subscription at period end, and processes Stripe webhooks with signature
verification and idempotent event handling — plus the pre-existing
plan-tier limit data and enforcement, unchanged.

This supersedes the earlier state (53 lines of plan-tier bookkeeping only,
docstring claiming "Stripe billing" that the code didn't implement)
described in prior audit passes.

| Piece | Status | Evidence |
|---|---|---|
| Plan tier data (`FREE`/`STARTER`/`PROFESSIONAL`/`ENTERPRISE` limits) | 🟢 (pre-existing, unchanged) | `app/subscriptions/models.py:16-19`, `PLAN_LIMITS` from line ~38 |
| Plan-limit enforcement (`check_plan_limit`) | 🟢 (pre-existing, unchanged) | `app/subscriptions/service.py:41` |
| Usage recording (`record_api_usage`) | 🟢 (pre-existing, unchanged) | `app/subscriptions/service.py:51` |
| Stripe SDK integration (checkout, billing portal, cancel, webhook) | 🟢 | `app/subscriptions/stripe_client.py` — every `stripe.*` call isolated here |
| Checkout / billing portal / cancel service logic | 🟢 | `app/subscriptions/service.py:67` (`create_checkout_session`), `:91` (`create_billing_portal_session`), `:101` (`cancel_subscription`) |
| Webhook signature verification + idempotent processing | 🟢 | `app/subscriptions/service.py:133` (`handle_webhook_event`); dedup via `StripeWebhookEvent` table, `models.py:207` |
| `stripe` package in `requirements.txt` | 🟢 | `stripe>=11.0` |
| Router exposing subscription/billing endpoints | 🟢 | `app/subscriptions/router.py` — `GET /subscriptions/me`, `POST /checkout`, `POST /portal`, `POST /cancel`, `POST /webhooks/stripe`; registered in `app/main.py` |
| Secrets via environment, never hard-coded | 🟢 | `app/config.py` — `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, price ids via `STRIPE_PRICE_<PLAN>_<INTERVAL>` env vars |
| Migrations | 🟢 | `subscriptions_initial.py`, `organizations_teams_initial.py` (see source-location.md) |
| WooCommerce `payment_method_title` field (unchanged) | 🟢 (still just a read-only display field synced from WooCommerce, not this gateway) | `frontend-fte/lib/api.ts` |

## Status

```text
Implementation: COMPLETE
Automated tests: PASS — 17 tests in backend-fte/tests/test_subscriptions.py,
  covering checkout, billing portal, cancellation, webhook signature
  verification, webhook idempotency (duplicate event id recognized and
  skipped), and every handled event type. All mock-based: StripeClient is
  patched, so no network call to Stripe is made and no API key is needed
  to run them.
Live Stripe verification: NOT VERIFIED — this has not been exercised
  against a real or Stripe-test-mode account. Verifying it live requires:
  setting STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / at least one
  STRIPE_PRICE_<PLAN>_<INTERVAL>, running an actual Checkout Session to
  completion, and delivering a real webhook (or using the Stripe CLI's
  `stripe trigger` / `stripe listen --forward-to`) to confirm the
  signature verification and event handlers behave as the mocked tests
  assume. Do not treat the automated test pass above as live verification
  — it isn't one.
```

## Full detail

See `source-location.md` for exact file/line references and the full
migration list.
