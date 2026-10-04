# Stripe sandbox setup

This integration accepts sandbox payments only. It does not configure tax,
enable real charges, or interpret a checkout redirect as proof of payment.

## Private backend configuration

Keep these in `backend/.env`, never in the frontend or Git:

```dotenv
STRIPE_SECRET_KEY=sk_test_REPLACE_PRIVATELY
STRIPE_PRICE_ID=price_1UMpGtJ2uPtu69mu9AaYMR6r
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_PRIVATELY
STRIPE_RETURN_URL=http://127.0.0.1:5173/
STRIPE_EXPECTED_PRICE_MYR=50
PRO_AI_ALLOWANCE_MYR=25
BILLING_USD_TO_MYR=4.09
```

The FX value is configurable, not a live rate feed. Each verified paid period
stores its own RM25 allowance, exchange rate and corresponding USD budget.
Changing settings affects future paid periods, not existing ones. Recorded AI
costs remain estimates pending reconciliation with provider billing.

## Local payment notifications

Stripe cannot deliver notifications directly to a loopback address. Install the
Stripe CLI, sign in to the SAME sandbox as the Price ID, then forward events:

```text
stripe listen --all-snapshot --forward-to http://127.0.0.1:8000/billing/webhook
```

Save the listener's `whsec_...` signing secret privately in `STRIPE_WEBHOOK_SECRET`
and restart the backend. Keep the listener running while testing. A Dashboard
webhook signing secret is different from a CLI listener signing secret.

The installed CLI requires an explicit event selection. `--all-snapshot` avoids
PowerShell converting an unquoted comma-separated `--events` list into a
space-separated array, which silently prevents matching payment events. If
using `--events` instead, quote the entire comma-separated list.

Alternatively, configure a sandbox event destination using a reachable HTTPS
test deployment's `/billing/webhook` URL and use that destination's secret.

Subscribe to:

- `checkout.session.completed`, `checkout.session.async_payment_succeeded`
- `invoice.paid`, `invoice.payment_failed`
- `customer.subscription.created`, `customer.subscription.updated`
- `customer.subscription.deleted`, `customer.subscription.paused`,
  `customer.subscription.resumed`

Enable the sandbox customer portal in Stripe Settings → Billing → Customer
portal. Allow payment-method updates and cancellation at period end. Avoid
enabling plan switches, trials, coupons or prorated changes: this initial
integration supports one full-price monthly Pro product only.

## Website test

1. Open Usage and choose Upgrade to Pro. Until the webhook secret is configured,
   the button remains disabled to avoid accepting untracked payments.
2. Complete Stripe-hosted checkout using Stripe test card data, never a real card.
3. Verify that a signed payment notification activates Pro and creates one paid
   usage period. Refresh Usage after checkout if delivery is still pending.
4. Replay notifications: neither the same event nor another event for the same
   invoice/period should replenish usage.
5. Test renewal, failed-payment recovery and cancellation using the sandbox.
   Only a verified paid renewal creates a fresh allowance; nothing rolls over.
6. Verify exhausted and inactive periods block before paid AI calls.

Before live deployment, separately review tax, refund/dispute handling, credit
reservation/concurrency, price changes, SDK/API upgrades, operational webhook
monitoring, and reconciliation of estimated AI cost with provider charges.

## Storage and access

`billing_accounts`, `billing_periods` and `billing_events` are backend-only
tables with RLS enabled and no anonymous/authenticated Data API privileges.
Checkout and portal endpoints use the signed-in user's customer mapping, not
customer IDs or prices supplied by the browser. Event acknowledgement and
allowance updates occur in one transaction; Stripe can safely retry failures.

## FPX one-month pass

FPX uses separate one-off Checkout (`mode=payment`), not the recurring price.
The RM50 pass grants the same RM25 AI-cost allowance for one calendar month
from the verified payment's transaction date. Month-end dates are clamped to
the following month's last day. Renewal is manual, after the pass expires.
An active card subscription or pass blocks overlapping purchases.

Activate FPX in the SAME sandbox's Settings → Payment methods. Then set
`STRIPE_FPX_ENABLED=true` privately in `backend/.env` and restart the backend.
Checkout also verifies Stripe's current default FPX configuration is available
and enabled. The Endive API uses `allowed_payment_method_types[0]=fpx` to filter
eligible methods; this does not activate FPX by itself.

Use a separate trial account for the website test; do not cancel the existing
active card subscription just to test FPX. Choose **Pay with FPX**, select a test
bank, and use Stripe's sandbox authorization/failure page. Never enter real bank
credentials. Verify successful authorization activates the pass only after the
signed notification; failure/cancellation grants no allowance. Keep the listener
running and check duplicate-event delivery does not replenish the balance.

`billing_fpx_orders` is backend-only, with RLS and revoked browser grants. Each
pending order snapshots its price, allowance and FX value; payment/session IDs
are unique. A fully paid conflict is retained as `review` and shown to the user
instead of replacing existing access. Refund/dispute automation remains part of
the separate production-readiness review.

Existing manually provisioned development Pro accounts retain their legacy
calendar-month budget. Newly purchased subscriptions use verified paid periods.
