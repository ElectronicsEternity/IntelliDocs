"""Sandbox subscription checkout and verified, idempotent payment reconciliation."""

from datetime import datetime, timezone
from decimal import Decimal
import logging
import re
import ssl
from urllib.parse import urlparse

import httpx
import stripe
import truststore
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.config import settings
from app.database.connection import get_connection

logger = logging.getLogger(__name__)
EVENT_TYPES = {
    "checkout.session.completed", "checkout.session.async_payment_succeeded",
    "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted", "customer.subscription.paused",
    "customer.subscription.resumed", "invoice.paid", "invoice.payment_failed",
}


def object_id(value):
    # Stripe expandable fields can be either an ID or an expanded object.
    return value.get("id") if isinstance(value, dict) else value


def timestamp(value):
    return datetime.fromtimestamp(int(value), timezone.utc)


def cancellation_at_period_end(subscription):
    """Recognize both Stripe representations of end-of-period cancellation."""
    if subscription.get("cancel_at_period_end") is True:
        return True
    items = subscription.get("items", {}).get("data", [])
    # An explicit date only represents period-end cancellation when it matches
    # this single-plan subscription's period end; other dates must not be guessed.
    end = items[0].get("current_period_end", subscription.get("current_period_end")) if len(items) == 1 else None
    return bool(end and subscription.get("cancel_at") == end)


class StripeGateway:
    """Keep Stripe credentials and certificate validation on the server."""

    def request(self, method, path, data=None, idempotency_key=None):
        key = settings.STRIPE_SECRET_KEY
        if not key or (settings.STRIPE_SANDBOX_ONLY and not key.startswith(("sk_test_", "rk_test_"))):
            raise HTTPException(503, "Stripe sandbox payments are not configured.")
        headers = {
            "Authorization": f"Bearer {key}",
            "Stripe-Version": "2026-09-30.endive",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            # Use the OS certificate store; never disable HTTPS verification.
            with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=20) as client:
                response = client.request(method, f"https://api.stripe.com/v1/{path}", headers=headers, data=data)
            if not response.is_success:
                # Log structured diagnostics without the provider's free-text
                # message, which could contain customer information or secrets.
                try:
                    error = response.json().get("error", {})
                except ValueError:
                    error = {}
                logger.warning(
                    "Stripe API failed: HTTP %s, resource=%s, type=%s, code=%s, parameter=%s",
                    response.status_code, path.split("/", 1)[0].split("?", 1)[0],
                    error.get("type"), error.get("code"), error.get("param"),
                )
                raise HTTPException(502, "Stripe could not complete this request. Please try again.")
            return response.json()
        except httpx.HTTPError as exc:
            logger.warning("Stripe connection failed (%s)", type(exc).__name__)
            raise HTTPException(502, "Stripe is temporarily unavailable. Please try again.") from None


def valid_price(price):
    # Validate currency, cadence, amount and mode rather than trusting an ID alone.
    recurring = price.get("recurring") or {}
    return (
        price.get("id") == settings.STRIPE_PRICE_ID
        and price.get("active") is True and price.get("livemode") is False
        and price.get("currency") == "myr"
        and price.get("unit_amount") == int(Decimal(str(settings.STRIPE_EXPECTED_PRICE_MYR)) * 100)
        and recurring.get("interval") == "month" and recurring.get("interval_count") == 1
        and recurring.get("usage_type") == "licensed"
    )


def paid_period(subscription, invoice):
    """Only a paid, full monthly invoice can grant a fresh allowance."""
    items = subscription.get("items", {}).get("data", [])
    if (subscription.get("status") != "active" or subscription.get("livemode") is not False
            or subscription.get("pause_collection") or len(items) != 1):
        return None
    item = items[0]
    if object_id(item.get("price")) != settings.STRIPE_PRICE_ID or item.get("quantity") != 1:
        return None
    if (invoice.get("status") != "paid" or invoice.get("livemode") is not False
            or invoice.get("billing_reason") not in {"subscription_create", "subscription_cycle"}
            or invoice.get("currency") != "myr"
            or invoice.get("amount_paid", 0) < int(Decimal(str(settings.STRIPE_EXPECTED_PRICE_MYR)) * 100)
            or object_id(invoice.get("customer")) != object_id(subscription.get("customer"))):
        return None
    start = item.get("current_period_start", subscription.get("current_period_start"))
    end = item.get("current_period_end", subscription.get("current_period_end"))
    if not start or not end or end <= start:
        return None
    # Match the invoice line's exact subscription item and period. A paid
    # one-off invoice or proration must never create another monthly allowance.
    for line in invoice.get("lines", {}).get("data", []):
        details = (line.get("parent") or {}).get("subscription_item_details") or {}
        line_item = details.get("subscription_item") or line.get("subscription_item")
        period = line.get("period") or {}
        if (line_item == item.get("id") and not details.get("proration", line.get("proration", False))
                and period.get("start") == start and period.get("end") == end):
            return timestamp(start), timestamp(end)
    return None


class BillingService:
    def __init__(self, gateway=None):
        self.gateway = gateway or StripeGateway()

    @staticmethod
    def ready():
        # Do not accept payments until their signed notifications can be handled.
        return bool(settings.STRIPE_SECRET_KEY.startswith(("sk_test_", "rk_test_"))
                    and settings.STRIPE_PRICE_ID.startswith("price_")
                    and settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_"))

    @staticmethod
    def return_url():
        url = settings.STRIPE_RETURN_URL
        parsed = urlparse(url)
        if (not parsed.hostname or parsed.username or parsed.password
                or (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}))
                or parsed.query or parsed.fragment):
            raise HTTPException(503, "The billing return address is not configured correctly.")
        return url

    def status(self, user_id):
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # Read the paid-period date for display without changing entitlement
            # snapshots or exposing another customer's subscription information.
            cur.execute("""SELECT a.subscription_status, a.cancel_at_period_end,
                f.period_end AS pass_end,
                EXISTS (SELECT 1 FROM billing_fpx_orders r WHERE r.user_id=a.user_id
                    AND r.status='review') AS payment_review,
                (SELECT p.period_end FROM billing_periods p
                 WHERE p.user_id=a.user_id AND p.subscription_id=a.subscription_id
                 ORDER BY p.period_start DESC LIMIT 1) AS period_end
                FROM billing_accounts a LEFT JOIN LATERAL (
                    SELECT period_end FROM billing_fpx_orders WHERE user_id=a.user_id
                    AND status='paid' AND (a.subscription_id IS NULL OR
                        a.subscription_status IN ('none','canceled','incomplete_expired'))
                    ORDER BY period_start DESC LIMIT 1
                ) f ON true WHERE a.user_id=%s""", (user_id,))
            account = cur.fetchone() or {}
        pass_end = account.get('pass_end')
        pass_active = bool(pass_end and pass_end > datetime.now(timezone.utc))
        return {
            "enabled": self.ready(), "sandbox": True,
            "fpx_enabled": self.ready() and settings.STRIPE_FPX_ENABLED,
            "payment_review": account.get('payment_review', False),
            "monthly_price_myr": settings.STRIPE_EXPECTED_PRICE_MYR,
            "subscription_status": ('pass_active' if pass_active else 'pass_expired') if pass_end else account.get("subscription_status", "none"),
            "access_type": 'fpx' if pass_end else 'subscription',
            "cancel_at_period_end": False if pass_end else account.get("cancel_at_period_end", False),
            "period_end": (pass_end or account.get('period_end')).isoformat() if pass_end or account.get('period_end') else None,
            "has_customer": bool(account),
        }

    @staticmethod
    def lock(cur, user_id):
        # Transaction-scoped per-user lock prevents simultaneous checkout and
        # webhook writes from creating duplicate subscriptions or stale state.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (user_id,))

    def checkout(self, user_id, payment_method='card'):
        if payment_method not in {'card', 'fpx'}:
            raise HTTPException(400, 'Unsupported payment method.')
        if not self.ready():
            raise HTTPException(503, "Stripe sandbox setup is awaiting payment-notification configuration.")
        if payment_method == 'fpx':
            if not settings.STRIPE_FPX_ENABLED:
                raise HTTPException(503, 'FPX is awaiting activation in Stripe.')
            configs = self.gateway.request('GET', 'payment_method_configurations')
            # allowed_payment_method_types filters the eligible Dashboard methods;
            # it does not activate a method that Stripe says is unavailable.
            available = any(c.get('is_default') and c.get('active') and
                c.get('fpx', {}).get('available') and
                c.get('fpx', {}).get('display_preference', {}).get('value') == 'on'
                for c in configs.get('data', []))
            if not available:
                raise HTTPException(503, 'Enable FPX in this Stripe sandbox before testing bank payments.')
        price = self.gateway.request("GET", f"prices/{settings.STRIPE_PRICE_ID}")
        if not valid_price(price):
            raise HTTPException(503, "The configured price must be the RM50 monthly sandbox Pro price.")
        return_url = self.return_url()
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            self.lock(cur, user_id)
            cur.execute("INSERT INTO user_accounts (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            cur.execute("SELECT * FROM billing_accounts WHERE user_id=%s FOR UPDATE", (user_id,))
            account = cur.fetchone()
            if not account:
                customer = self.gateway.request("POST", "customers", {"metadata[user_id]": user_id}, f"intellidocs-customer-{user_id}")
                cur.execute("INSERT INTO billing_accounts (user_id, customer_id) VALUES (%s,%s) RETURNING *", (user_id, customer["id"]))
                account = cur.fetchone()
            customer_id = account["customer_id"]
            # A bank pass is not a top-up: prevent overlap and lost allowance.
            cur.execute("""SELECT 1 FROM billing_fpx_orders WHERE user_id=%s
                AND status='paid' AND period_end>now() LIMIT 1""", (user_id,))
            if cur.fetchone():
                raise HTTPException(409, 'Your Pro pass is still active. Renew after it ends.')
            # Check Stripe too: a completed checkout may precede its webhook.
            subscriptions = self.gateway.request("GET", f"subscriptions?customer={customer_id}&status=all&limit=100")
            if subscriptions.get("has_more") or any(s["status"] not in {"canceled", "incomplete_expired"} for s in subscriptions["data"]):
                raise HTTPException(409, "A subscription already exists. Use Manage subscription instead.")
            if account.get("checkout_session_id"):
                session = self.gateway.request("GET", f"checkout/sessions/{account['checkout_session_id']}")
                if session.get("status") == "open":
                    expected_mode = 'payment' if payment_method == 'fpx' else 'subscription'
                    if session.get('mode', 'subscription') == expected_mode:
                        return {"url": session["url"]}
                    # Switching the chosen payment option closes only the user's
                    # uncompleted checkout, not any paid subscription or pass.
                    self.gateway.request('POST', f"checkout/sessions/{session['id']}/expire")
                elif session.get('status') == 'complete' and session.get('payment_status') != 'paid':
                    raise HTTPException(409, 'Your previous payment is still processing. Please wait.')
                elif session.get('status') == 'complete' and session.get('mode') == 'payment':
                    cur.execute('SELECT status FROM billing_fpx_orders WHERE checkout_session_id=%s', (session['id'],))
                    order = cur.fetchone()
                    if order and order['status'] != 'paid':
                        raise HTTPException(409, 'Your bank payment is awaiting confirmation. Please wait.')
            # One hourly idempotency window also protects against a lost response
            # before the new checkout ID has been persisted in the database.
            window = int(datetime.now(timezone.utc).timestamp()) // 3600
            data = {
                "mode": "subscription", "customer": customer_id,
                "client_reference_id": user_id, "subscription_data[metadata][user_id]": user_id,
                "line_items[0][price]": settings.STRIPE_PRICE_ID, "line_items[0][quantity]": "1",
                # Current Checkout API versions select eligible recurring
                # payment methods from the sandbox Dashboard configuration.
                # The old payment_method_types parameter is no longer accepted.
                "success_url": f"{return_url}?billing=success", "cancel_url": f"{return_url}?billing=cancelled",
                # Tax setup belongs to the user; do not silently enable Stripe Tax.
            }
            if payment_method == 'fpx':
                # Use a one-off price for the same verified product. FPX cannot
                # use its recurring price or authorize automatic bank renewals.
                data.pop('subscription_data[metadata][user_id]')
                data.pop('line_items[0][price]')
                data.update({'mode': 'payment', 'allowed_payment_method_types[0]': 'fpx',
                    'line_items[0][price_data][currency]': 'myr',
                    'line_items[0][price_data][unit_amount]': str(price['unit_amount']),
                    'line_items[0][price_data][product]': object_id(price['product']),
                    'metadata[pass_type]': 'intellidocs_fpx_month_v1'})
            session = self.gateway.request("POST", "checkout/sessions", data,
                f"intellidocs-checkout-v3-{payment_method}-{user_id}-{window}-{account.get('checkout_session_id') or 'first'}")
            if payment_method == 'fpx':
                allowance = Decimal(str(settings.PRO_AI_ALLOWANCE_MYR))
                rate = Decimal(str(settings.BILLING_USD_TO_MYR))
                if allowance <= 0 or rate <= 0:
                    raise HTTPException(503, 'The Pro allowance is not configured correctly.')
                cur.execute("""INSERT INTO billing_fpx_orders (checkout_session_id,user_id,
                    amount_myr,allowance_myr,usd_to_myr,budget_usd) VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING""", (session['id'], user_id,
                    Decimal(price['unit_amount']) / 100, allowance, rate, allowance / rate))
            cur.execute("""UPDATE billing_accounts SET checkout_session_id=%s, checkout_url=%s,
                checkout_expires_at=%s, updated_at=now() WHERE user_id=%s""",
                (session["id"], session["url"], timestamp(session["expires_at"]), user_id))
            return {"url": session["url"]}

    def portal(self, user_id):
        if not self.ready():
            raise HTTPException(503, "Stripe sandbox payments are not configured.")
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM billing_accounts WHERE user_id=%s", (user_id,))
            account = cur.fetchone()
        if not account:
            raise HTTPException(409, "This account does not have a Stripe subscription yet.")
        session = self.gateway.request("POST", "billing_portal/sessions", {"customer": account[0], "return_url": self.return_url()})
        return {"url": session["url"]}

    def webhook(self, payload, signature):
        if not self.ready():
            raise HTTPException(503, "Stripe payment notifications are not configured.")
        try:
            # The SDK checks HMAC and timestamp tolerance against the raw bytes.
            event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET, tolerance=300).to_dict()
        except (ValueError, stripe.SignatureVerificationError):
            raise HTTPException(400, "Invalid Stripe notification signature.") from None
        self._apply_verified_event(event)

    def recover_event(self, event_id):
        """Server-side recovery of a missed event; never trust a supplied payload."""
        # Fetch the original event with the backend's authenticated Stripe key.
        # This is a maintenance method, not an unsigned webhook or public route.
        if not re.fullmatch(r"evt_[A-Za-z0-9]+", event_id):
            raise HTTPException(400, "Invalid Stripe event identifier.")
        event = self.gateway.request("GET", f"events/{event_id}")
        if event.get("id") != event_id:
            raise HTTPException(502, "Stripe returned an unexpected event.")
        self._apply_verified_event(event)

    def _apply_verified_event(self, event):
        # Only signature-verified webhooks or authenticated Stripe event reads
        # enter here. Both use the same ownership, replay and payment checks.
        if event.get("livemode") is not False:
            raise HTTPException(400, "Only sandbox notifications are accepted.")
        if event["type"] not in EVENT_TYPES:
            return
        obj = event["data"]["object"]
        if event['type'].startswith('checkout.session.') and obj.get('mode') == 'payment':
            # This branch still follows signature verification above; the handler
            # re-fetches the session/payment and requires a local pending order.
            from app.services.fpx import apply_fpx_event
            apply_fpx_event(self, event)
            return
        customer_id = object_id(obj.get("customer"))
        if event["type"].startswith("customer.subscription."):
            subscription_id = obj["id"]
        else:
            parent = obj.get("parent") or {}
            subscription_id = object_id(obj.get("subscription") or (parent.get("subscription_details") or {}).get("subscription"))
        if not customer_id or not subscription_id:
            return
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT user_id FROM billing_accounts WHERE customer_id=%s", (customer_id,))
            owner = cur.fetchone()
            if not owner:
                return  # Unrelated sandbox products/customers must not grant access.
            user_id = owner["user_id"]
            self.lock(cur, user_id)
            cur.execute("SELECT 1 FROM billing_events WHERE event_id=%s", (event["id"],))
            if cur.fetchone():
                return
            # Re-fetch canonical state AFTER locking. Webhooks can arrive out of
            # order; an old failed-payment event must not undo a later payment.
            subscription = self.gateway.request("GET", f"subscriptions/{subscription_id}?expand[]=latest_invoice")
            if object_id(subscription.get("customer")) != customer_id:
                raise HTTPException(400, "Stripe subscription ownership mismatch.")
            cur.execute("SELECT subscription_id FROM billing_accounts WHERE user_id=%s", (user_id,))
            existing = cur.fetchone()["subscription_id"]
            if existing and existing != subscription_id:
                current = self.gateway.request("GET", f"subscriptions/{existing}")
                if current.get("status") not in {"canceled", "incomplete_expired"}:
                    return
                if subscription.get("status") in {"canceled", "incomplete_expired"}:
                    return  # Delayed old cancellation cannot overwrite a new subscription.
            items = subscription.get("items", {}).get("data", [])
            matching = (len(items) == 1 and object_id(items[0].get("price")) == settings.STRIPE_PRICE_ID)
            subscription_status = subscription.get("status", "unknown") if matching else "unsupported_price"
            cur.execute("""UPDATE billing_accounts SET subscription_id=%s, subscription_status=%s,
                cancel_at_period_end=%s, updated_at=now() WHERE user_id=%s""",
                (subscription_id, subscription_status, cancellation_at_period_end(subscription), user_id))
            invoice = subscription.get("latest_invoice")
            if isinstance(invoice, str):
                invoice = self.gateway.request("GET", f"invoices/{invoice}")
            period = paid_period(subscription, invoice or {}) if matching else None
            if period:
                allowance = Decimal(str(settings.PRO_AI_ALLOWANCE_MYR))
                rate = Decimal(str(settings.BILLING_USD_TO_MYR))
                if allowance <= 0 or rate <= 0:
                    raise HTTPException(503, "The Pro allowance is not configured correctly.")
                # Unique invoice identity prevents replay from resetting credits;
                # immutable period snapshots prevent rollover and rate drift.
                cur.execute("""INSERT INTO billing_periods (invoice_id,user_id,subscription_id,
                    period_start,period_end,allowance_myr,usd_to_myr,budget_usd)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (invoice["id"], user_id, subscription_id, *period, allowance, rate, allowance / rate))
                cur.execute("UPDATE user_accounts SET plan_code='pro', updated_at=now() WHERE user_id=%s", (user_id,))
            # Event acknowledgement and entitlement updates commit together. If
            # an API/database error occurs, rollback allows Stripe to retry safely.
            cur.execute("INSERT INTO billing_events (event_id,event_type) VALUES (%s,%s)", (event["id"], event["type"]))
