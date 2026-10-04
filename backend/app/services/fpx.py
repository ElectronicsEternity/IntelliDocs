"""One-off FPX passes: verified bank payment, fixed allowance, manual renewal."""
import calendar
from datetime import datetime, timezone
from decimal import Decimal

from psycopg.rows import dict_row

from app.database.connection import get_connection


def next_month(start):
    # Clamp dates such as 31 January to the last day of the following month.
    year = start.year + (start.month == 12)
    month = start.month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def verified_payment(session, intent, customer_id, amount_myr):
    """A redirect or an unpaid Checkout event is never proof of payment."""
    charge = intent.get('latest_charge') or {}
    amount = int(Decimal(str(amount_myr)) * 100)
    return (
        session.get('livemode') is False and session.get('mode') == 'payment'
        and session.get('status') == 'complete' and session.get('payment_status') == 'paid'
        and session.get('customer') == customer_id and session.get('currency') == 'myr'
        and session.get('amount_total') == amount
        and intent.get('livemode') is False and intent.get('status') == 'succeeded'
        and intent.get('customer') == customer_id and intent.get('currency') == 'myr'
        and intent.get('amount_received') == amount
        and isinstance(charge, dict) and charge.get('paid') is True
        and charge.get('captured') is True and not charge.get('refunded')
        and charge.get('amount_refunded', 0) == 0
        and charge.get('payment_method_details', {}).get('type') == 'fpx'
        and bool(charge.get('created'))
    )


def apply_fpx_event(service, event):
    """Use canonical Stripe objects and a server-created order, not event metadata."""
    session_id = event['data']['object']['id']
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM billing_fpx_orders WHERE checkout_session_id=%s', (session_id,))
        order = cur.fetchone()
        if not order:
            return  # Ignore payments for products not created by our pass checkout.
        user_id = order['user_id']
        service.lock(cur, user_id)
        cur.execute('SELECT 1 FROM billing_events WHERE event_id=%s', (event['id'],))
        if cur.fetchone():
            return
        # Read again after the lock: completed and async-success events can race.
        cur.execute('SELECT * FROM billing_fpx_orders WHERE checkout_session_id=%s FOR UPDATE', (session_id,))
        order = cur.fetchone()
        if order['status'] != 'pending':
            return  # A second event must never reset an existing pass allowance.
        cur.execute('SELECT * FROM billing_accounts WHERE user_id=%s', (user_id,))
        account = cur.fetchone()
        session = service.gateway.request('GET', f'checkout/sessions/{session_id}?expand[]=payment_intent.latest_charge')
        if session.get('id') != session_id:
            raise ValueError('Unexpected Stripe checkout session')
        intent = session.get('payment_intent')
        if isinstance(intent, str):
            intent = service.gateway.request('GET', f'payment_intents/{intent}?expand[]=latest_charge')
        if not verified_payment(session, intent or {}, account['customer_id'], order['amount_myr']):
            return  # Leave unpaid orders pending so the later success can reconcile.
        # Do not overwrite a subscription or overlapping pass. Keep a paid
        # conflict for manual review instead of silently charging without access.
        cur.execute("""SELECT 1 FROM billing_fpx_orders WHERE user_id=%s
            AND status='paid' AND period_end>now() LIMIT 1""", (user_id,))
        overlap = bool(cur.fetchone())
        if account.get('subscription_id'):
            current = service.gateway.request('GET', f"subscriptions/{account['subscription_id']}")
            overlap = overlap or current.get('status') not in {'canceled', 'incomplete_expired'}
        if overlap:
            cur.execute("UPDATE billing_fpx_orders SET status='review',payment_intent_id=%s WHERE checkout_session_id=%s",
                        (intent['id'], session_id))
            raise_review = True
        else:
            raise_review = False
            start = datetime.fromtimestamp(intent['latest_charge']['created'], timezone.utc)
            cur.execute("""UPDATE billing_fpx_orders SET status='paid',payment_intent_id=%s,
                period_start=%s,period_end=%s WHERE checkout_session_id=%s""",
                (intent['id'], start, next_month(start), session_id))
            cur.execute("UPDATE user_accounts SET plan_code='pro',updated_at=now() WHERE user_id=%s", (user_id,))
        cur.execute('INSERT INTO billing_events (event_id,event_type) VALUES (%s,%s)', (event['id'], event['type']))
    if raise_review:
        # No provider payload or customer details are logged.
        import logging
        logging.getLogger(__name__).warning('Paid FPX order requires overlap review')
