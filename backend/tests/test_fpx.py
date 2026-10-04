"""FPX tests use canonical fixtures, never real bank or AI requests."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
import pytest

from app.config import settings
from app.services.billing import BillingService
from app.services.fpx import next_month, verified_payment, apply_fpx_event
from test_billing import MemoryConnection, MemoryCursor, sandbox_config


def payment():
    session = {'id': 'cs_fpx', 'livemode': False, 'mode': 'payment', 'status': 'complete',
        'payment_status': 'paid', 'customer': 'cus_fixture', 'currency': 'myr', 'amount_total': 5000}
    intent = {'id': 'pi_fpx', 'livemode': False, 'status': 'succeeded', 'customer': 'cus_fixture',
        'currency': 'myr', 'amount_received': 5000, 'latest_charge': {'created': 1791158400,
        'paid': True, 'captured': True, 'refunded': False, 'amount_refunded': 0,
        'payment_method_details': {'type': 'fpx'}}}
    session['payment_intent'] = intent
    return session, intent


@pytest.mark.parametrize('month,day,expected', [(1,31,(2026,2,28)), (12,31,(2027,1,31)), (3,15,(2026,4,15))])
def test_calendar_month_expiry(month, day, expected):
    result = next_month(datetime(2026,month,day,12,tzinfo=timezone.utc))
    assert (result.year,result.month,result.day) == expected
    assert result.hour == 12


@pytest.mark.parametrize('mutation', ['valid','unpaid','live','wrong_customer','wrong_currency','wrong_amount','card','refunded','uncaptured','failed'])
def test_only_full_verified_fpx_payments_qualify(mutation):
    session, intent = payment()
    if mutation == 'unpaid': session['payment_status'] = 'unpaid'
    if mutation == 'live': intent['livemode'] = True
    if mutation == 'wrong_customer': intent['customer'] = 'cus_other'
    if mutation == 'wrong_currency': session['currency'] = 'usd'
    if mutation == 'wrong_amount': intent['amount_received'] = 4999
    if mutation == 'card': intent['latest_charge']['payment_method_details']['type'] = 'card'
    if mutation == 'refunded': intent['latest_charge']['amount_refunded'] = 1
    if mutation == 'uncaptured': intent['latest_charge']['captured'] = False
    if mutation == 'failed': intent['status'] = 'requires_payment_method'
    assert bool(verified_payment(session, intent, 'cus_fixture', Decimal('50'))) == (mutation == 'valid')


class FpxConnection(MemoryConnection):
    def __init__(self):
        super().__init__()
        self.order = {'checkout_session_id':'cs_fpx', 'user_id':'user-a', 'status':'pending',
            'amount_myr':Decimal('50'), 'budget_usd':Decimal('6.25')}
        self.overlap = False
    def cursor(self, **_kwargs): return FpxCursor(self)


class FpxCursor(MemoryCursor):
    def execute(self, sql, params):
        sql = ' '.join(sql.split())
        if sql.startswith('SELECT * FROM billing_fpx_orders'):
            self.conn.result = deepcopy(self.conn.order) if params[0] == 'cs_fpx' else None
        elif sql.startswith('SELECT 1 FROM billing_fpx_orders'):
            self.conn.result = {'present':True} if self.conn.overlap else None
        elif sql.startswith('UPDATE billing_fpx_orders SET status='):
            self.conn.order['status'] = 'review' if "status='review'" in sql else 'paid'
            self.conn.order['payment_intent_id'] = params[0]
            if self.conn.order['status'] == 'paid':
                self.conn.order.update(period_start=params[1],period_end=params[2])
        elif sql.startswith('INSERT INTO billing_fpx_orders'):
            self.conn.order.update(checkout_session_id=params[0],amount_myr=params[2],
                allowance_myr=params[3],usd_to_myr=params[4],budget_usd=params[5])
        else:
            super().execute(sql, params)


def fpx_service(monkeypatch):
    conn = FpxConnection()
    session, _intent = payment()
    class Gateway:
        def request(self, *_args): return deepcopy(session)
    monkeypatch.setattr('app.services.fpx.get_connection', lambda:conn)
    return BillingService(Gateway()), conn, session


def event(event_id='evt_fpx'):
    return {'id':event_id,'type':'checkout.session.completed','livemode':False,
            'data':{'object':{'id':'cs_fpx','mode':'payment'}}}


def test_paid_pass_is_idempotent_and_unpaid_can_recover(monkeypatch):
    service, conn, session = fpx_service(monkeypatch)
    session['payment_status'] = 'unpaid'
    apply_fpx_event(service,event())
    assert conn.order['status'] == 'pending' and conn.plan == 'trial'
    session['payment_status'] = 'paid'
    apply_fpx_event(service,event('evt_async_success'))
    assert conn.order['status'] == 'paid' and conn.plan == 'pro'
    saved = deepcopy(conn.order)
    apply_fpx_event(service,event('evt_duplicate'))
    assert conn.order == saved


def test_paid_overlap_is_flagged_not_silently_overwritten(monkeypatch):
    service, conn, _session = fpx_service(monkeypatch)
    conn.overlap = True
    apply_fpx_event(service,event())
    assert conn.order['status'] == 'review' and conn.plan == 'trial'


def test_fpx_checkout_requires_activation():
    with pytest.raises(HTTPException) as exc: BillingService().checkout('user-a','fpx')
    assert exc.value.status_code == 503


def test_fpx_checkout_uses_one_off_price_and_server_snapshot(monkeypatch):
    conn = FpxConnection()
    monkeypatch.setattr(settings,'STRIPE_FPX_ENABLED',True)
    calls = []
    class Gateway:
        def request(self, method, path, data=None, *_args):
            calls.append((method,path,data))
            if path == 'payment_method_configurations':
                return {'data':[{'is_default':True,'active':True,'fpx':{'available':True,'display_preference':{'value':'on'}}}]}
            if path.startswith('prices/'):
                return {'id':'price_fixture','product':'prod_fixture','active':True,'livemode':False,
                    'currency':'myr','unit_amount':5000,'recurring':{'interval':'month','interval_count':1,'usage_type':'licensed'}}
            if path.startswith('subscriptions?'): return {'data':[]}
            return {'id':'cs_fpx','url':'https://checkout.stripe.com/fixture','expires_at':1791158400}
    monkeypatch.setattr('app.services.billing.get_connection',lambda:conn)
    BillingService(Gateway()).checkout('user-a','fpx')
    data = next(c[2] for c in calls if c[:2] == ('POST','checkout/sessions'))
    assert data['mode'] == 'payment' and data['allowed_payment_method_types[0]'] == 'fpx'
    assert 'line_items[0][price]' not in data and 'subscription_data[metadata][user_id]' not in data
    assert data['line_items[0][price_data][unit_amount]'] == '5000'
    assert conn.order['budget_usd'] == Decimal('6.25')
