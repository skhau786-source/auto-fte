# Payment Integration — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/subscriptions/models.py           (PlanTier, SubscriptionStatus, PLAN_LIMITS — pre-existing;
                                                     Subscription model gains Stripe fields, line 140;
                                                     StripeWebhookEvent — idempotency ledger, line 207;
                                                     get_stripe_price_id/get_plan_for_price_id, lines 116/122)
backend-fte/app/subscriptions/service.py           (SubscriptionService — plan-limit checks, line 26, pre-existing;
                                                     create_checkout_session, line 67; create_billing_portal_session,
                                                     line 91; cancel_subscription, line 101; handle_webhook_event
                                                     (signature verify + idempotent dispatch), line 133;
                                                     per-event-type handlers, lines 194-283)
backend-fte/app/subscriptions/router.py            (GET /subscriptions/me, POST /checkout, POST /portal,
                                                     POST /cancel, POST /webhooks/stripe — lines 56/85/110/128/151)
backend-fte/app/subscriptions/schemas.py           (CheckoutSessionRequest/Out, BillingPortalOut, SubscriptionOut,
                                                     CancelSubscriptionOut, WebhookResultOut)
backend-fte/app/subscriptions/stripe_client.py     (StripeClient — thin wrapper isolating every stripe.* SDK call;
                                                     create_checkout_session, create_billing_portal_session,
                                                     cancel_subscription, construct_webhook_event)
backend-fte/app/subscriptions/exceptions.py        (SubscriptionError hierarchy: StripeNotConfiguredError,
                                                     UnknownPlanError, SubscriptionNotFoundError,
                                                     InvalidWebhookSignatureError)
backend-fte/app/config.py                          (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_SUCCESS_URL,
                                                     STRIPE_CANCEL_URL — all read from environment, never hard-coded;
                                                     empty by default, so billing endpoints raise
                                                     StripeNotConfiguredError rather than failing at import time)
backend-fte/app/main.py                            (subscriptions_router registered into the FastAPI app)
backend-fte/requirements.txt                       (stripe>=11.0)
```

**Migrations:**

```
backend-fte/alembic/versions/subscriptions_initial.py         (creates subscriptions, usage_records,
                                                                 stripe_webhook_events tables)
backend-fte/alembic/versions/organizations_teams_initial.py   (creates organizations/teams/organization_members —
                                                                 subscriptions.organization_id FK target; this
                                                                 migration was previously missing entirely, which
                                                                 would have broken `alembic upgrade head` against a
                                                                 real database before this table existed)
backend-fte/alembic/versions/merge_phase3_phase4_heads.py     (merges this branch's migration head with the
                                                                 Phase 4 head so `alembic upgrade head` resolves to
                                                                 a single head again)
```

**Status:**

```text
Implementation: COMPLETE — Stripe SDK integration, checkout session, billing
  portal session, cancel-at-period-end, and a webhook receiver with
  signature verification and idempotent event processing (event id
  recorded in stripe_webhook_events before being acted on, so a
  redelivered Stripe event is recognized and skipped rather than
  reapplied) are all present and wired into the router/app.
Automated tests: PASS — backend-fte/tests/test_subscriptions.py (17 tests
  across checkout, billing portal, cancellation, webhook signature/
  idempotency, and all handled event types: checkout.session.completed,
  customer.subscription.created/updated/deleted, invoice.payment_failed).
  All tests are mock-based — StripeClient is patched, the real `stripe`
  SDK is never called, no network access or live/test API key is used.
Live Stripe verification: NOT VERIFIED — no live or Stripe-test-mode
  credentials were available in the environment this was built in. The
  Checkout Session/Billing Portal URLs, and the webhook signature
  verification against a real `Stripe-Signature` header, have not been
  exercised against the actual Stripe API. STRIPE_SECRET_KEY and
  STRIPE_WEBHOOK_SECRET must be set (see app/config.py) and a real
  checkout/webhook flow run against them before this can be called
  live-verified.
```

**Secrets:** none of the above hard-codes a Stripe secret key, webhook
signing secret, or price id — all are read from environment variables
(`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_<PLAN>_<INTERVAL>`
in `models.py`). Confirmed via repository-wide secret scan before this
documentation update — see the pre-commit audit for that scan's results.

No snapshot exists — the implementation above is the only copy; do not
create a second "payments" or "billing" module.
