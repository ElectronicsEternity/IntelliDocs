"""Billing tests use signed fixtures and fake Stripe responses; no paid calls."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import time

from fastapi import HTTPException
import pytest

from app.api.billing_routes import get_billing_service
from app.config import settings
from app.main import app
from app.services.billing import BillingService, cancellation_at_period_end, paid_period, valid_price
from app.services.usage.plans import get_plan_limits
from app.services.usage.tracker import UsageTracker


@pytest.fixture(autouse=True)
def sandbox_config(monkeypatch):
    monkeypatch.setattr(settings, 'STRIPE_SECRET_KEY', 'sk_test_fixture')
    monkeypatch.setattr(settings, 'STRIPE_WEBHOOK_SECRET', 'whsec_fixture')
    monkeypatch.setattr(settings, 'STRIPE_PRICE_ID', 'price_fixture')
    monkeypatch.setattr(settings, 'STRIPE_EXPECTED_PRICE_MYR', 50)
    monkeypatch.setattr(settings, 'PRO_AI_ALLOWANCE_MYR', 25)
    monkeypatch.setattr(settings, 'BILLING_USD_TO_MYR', 4)
    monkeypatch.setattr(settings, 'STRIPE_FPX_ENABLED', False)


def subscription():
    return {
        'id': 'sub_fixture', 'customer': 'cus_fixture', 'status': 'active',
        'livemode': False, 'cancel_at_period_end': False,
        'items': {'data': [{'id': 'si_fixture', 'quantity': 1, 'price': {'id': 'price_fixture'},
                           'current_period_start': 1791072000, 'current_period_end': 1793750400}]},
        'latest_invoice': {
            'id': 'in_fixture', 'customer': 'cus_fixture', 'livemode': False,
            'status': 'paid', 'billing_reason': 'subscription_cycle', 'currency': 'myr',
            'amount_paid': 5000,
            'lines': {'data': [{'period': {'start': 1791072000, 'end': 1793750400},
                               'parent': {'subscription_item_details': {'subscription_item': 'si_fixture', 'proration': False}}}]},
        },
    }


def signed_event(event_type='invoice.paid', event_id='evt_fixture', livemode=False, signed_at=None):
    event = {'id': event_id, 'type': event_type, 'livemode': livemode,
             'data': {'object': {'customer': 'cus_fixture',
                                'parent': {'subscription_details': {'subscription': 'sub_fixture'}}}}}
    body = json.dumps(event).encode()
    stamp = int(time.time()) if signed_at is None else signed_at
    digest = hmac.new(b'whsec_fixture', str(stamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return body, f't={stamp},v1={digest}'


class MemoryConnection:
    """Model transaction rollback and the few writes used by the payment handler."""
    def __init__(self):
        self.account = {'user_id': 'user-a', 'customer_id': 'cus_fixture', 'subscription_id': None}
        self.events = set()
        self.periods = {}
        self.plan = 'trial'
        self.result = None

    def __enter__(self):
        self.saved = deepcopy((self.account, self.events, self.periods, self.plan))
        return self

    def __exit__(self, kind, *_args):
        if kind:
            self.account, self.events, self.periods, self.plan = self.saved

    def cursor(self, **_kwargs):
        return MemoryCursor(self)


class MemoryCursor:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self
    def __exit__(self, *_args): pass
    def fetchone(self): return self.conn.result

    def execute(self, sql, params):
        normalized = ' '.join(sql.split())
        conn = self.conn
        if normalized.startswith('SELECT user_id'):
            conn.result = {'user_id': 'user-a'} if params[0] == conn.account['customer_id'] else None
        elif normalized.startswith('SELECT pg_advisory'):
            pass
        elif normalized.startswith('SELECT 1 FROM billing_events'):
            conn.result = {'present': True} if params[0] in conn.events else None
        elif normalized.startswith('SELECT 1 FROM billing_fpx_orders'):
            conn.result = None
        elif normalized.startswith('SELECT subscription_id'):
            conn.result = {'subscription_id': conn.account['subscription_id']}
        elif normalized.startswith('INSERT INTO user_accounts'):
            pass
        elif normalized.startswith('SELECT * FROM billing_accounts'):
            conn.result = deepcopy(conn.account)
        elif normalized.startswith('UPDATE billing_accounts SET checkout_session_id'):
            conn.account.update(checkout_session_id=params[0], checkout_url=params[1], checkout_expires_at=params[2])
        elif normalized.startswith('UPDATE billing_accounts'):
            conn.account.update(subscription_id=params[0], subscription_status=params[1], cancel_at_period_end=params[2])
        elif normalized.startswith('INSERT INTO billing_periods'):
            conn.periods.setdefault(params[0], params)
        elif normalized.startswith('UPDATE user_accounts'):
            conn.plan = 'pro'
        elif normalized.startswith('INSERT INTO billing_events'):
            conn.events.add(params[0])
        else:
            raise AssertionError(f'Unexpected SQL: {normalized}')


def service_fixture(monkeypatch):
    conn = MemoryConnection()
    canonical = subscription()
    class Gateway:
        def __init__(self): self.calls = []
        def request(self, method, path, *_args):
            self.calls.append(path)
            assert method == 'GET'
            return deepcopy(canonical)
    gateway = Gateway()
    monkeypatch.setattr('app.services.billing.get_connection', lambda: conn)
    return BillingService(gateway), conn, canonical


def test_price_validation_checks_mode_currency_amount_and_cadence():
    price = {'id': 'price_fixture', 'active': True, 'livemode': False, 'currency': 'myr',
             'unit_amount': 5000, 'recurring': {'interval': 'month', 'interval_count': 1, 'usage_type': 'licensed'}}
    assert valid_price(price)
    for key, value in [('livemode', True), ('currency', 'usd'), ('unit_amount', 1000), ('active', False)]:
        assert not valid_price({**price, key: value})
    assert not valid_price({**price, 'recurring': {'interval': 'year'}})


def test_paid_invoice_grants_snapshot_once_even_with_different_event_ids(monkeypatch):
    service, conn, _canonical = service_fixture(monkeypatch)
    service.webhook(*signed_event())
    assert conn.plan == 'pro'
    assert conn.periods['in_fixture'][5:] == (Decimal('25'), Decimal('4'), Decimal('6.25'))
    service.webhook(*signed_event())
    monkeypatch.setattr(settings, 'PRO_AI_ALLOWANCE_MYR', 50)
    service.webhook(*signed_event(event_id='evt_second'))
    assert len(conn.periods) == 1
    assert conn.periods['in_fixture'][5] == Decimal('25')
    assert len(service.gateway.calls) == 2


def test_failure_and_recovery_follow_canonical_state_not_event_order(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    canonical['status'] = 'past_due'
    canonical['latest_invoice']['status'] = 'open'
    service.webhook(*signed_event('invoice.payment_failed'))
    assert not conn.periods and conn.plan == 'trial'
    canonical['status'] = 'active'
    canonical['latest_invoice']['status'] = 'paid'
    service.webhook(*signed_event('invoice.paid', 'evt_recovery'))
    service.webhook(*signed_event('invoice.payment_failed', 'evt_delayed_failure'))
    assert conn.account['subscription_status'] == 'active'
    assert len(conn.periods) == 1


def test_renewal_creates_new_period_without_carrying_old_allowance(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    service.webhook(*signed_event())
    item = canonical['items']['data'][0]
    item['current_period_start'] = item['current_period_end']
    item['current_period_end'] += 30 * 86400
    invoice = canonical['latest_invoice']
    invoice['id'] = 'in_renewal'
    invoice['lines']['data'][0]['period'] = {'start': item['current_period_start'], 'end': item['current_period_end']}
    service.webhook(*signed_event(event_id='evt_renewal'))
    assert len(conn.periods) == 2
    assert conn.periods['in_renewal'][-1] == Decimal('6.25')


def test_immediate_cancellation_records_inactive_subscription(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    service.webhook(*signed_event())
    canonical['status'] = 'canceled'
    service.webhook(*signed_event(event_id='evt_cancel'))
    assert conn.account['subscription_status'] == 'canceled'
    assert len(conn.periods) == 1


def test_cancel_at_period_end_keeps_paid_period(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    canonical['cancel_at_period_end'] = True
    service.webhook(*signed_event())
    assert conn.account['subscription_status'] == 'active'
    assert conn.account['cancel_at_period_end'] is True
    assert conn.plan == 'pro'


def test_explicit_cancellation_date_preserves_allowance_and_undo_clears_notice(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    service.webhook(*signed_event())
    saved_periods = deepcopy(conn.periods)
    canonical['cancel_at'] = canonical['items']['data'][0]['current_period_end']
    service.webhook(*signed_event(event_id='evt_explicit_cancel'))
    assert conn.account['cancel_at_period_end'] is True
    assert conn.account['subscription_status'] == 'active'
    assert conn.periods == saved_periods and conn.plan == 'pro'
    canonical['cancel_at'] = None
    service.webhook(*signed_event(event_id='evt_undo_cancel'))
    assert conn.account['cancel_at_period_end'] is False
    assert conn.periods == saved_periods


@pytest.mark.parametrize('offset', [-86400, 86400])
def test_other_explicit_dates_are_not_labeled_period_end(offset):
    canonical = subscription()
    canonical['cancel_at'] = canonical['items']['data'][0]['current_period_end'] + offset
    assert cancellation_at_period_end(canonical) is False


@pytest.mark.parametrize('mutation', ['unpaid', 'wrong_price', 'wrong_customer', 'proration', 'oneoff', 'wrong_period', 'paused', 'underpaid'])
def test_nonqualifying_invoices_never_grant_allowance(mutation):
    s = subscription()
    inv = s['latest_invoice']
    if mutation == 'unpaid': inv['status'] = 'open'
    if mutation == 'wrong_price': s['items']['data'][0]['price']['id'] = 'price_other'
    if mutation == 'wrong_customer': inv['customer'] = 'cus_other'
    if mutation == 'proration': inv['lines']['data'][0]['parent']['subscription_item_details']['proration'] = True
    if mutation == 'oneoff': inv['billing_reason'] = 'manual'
    if mutation == 'wrong_period': inv['lines']['data'][0]['period']['end'] += 1
    if mutation == 'paused': s['pause_collection'] = {'behavior': 'void'}
    if mutation == 'underpaid': inv['amount_paid'] = 4999
    assert paid_period(s, inv) is None


@pytest.mark.parametrize('kind', ['tampered', 'missing', 'expired', 'live'])
def test_invalid_notifications_do_not_touch_database(monkeypatch, kind):
    def forbidden(): raise AssertionError('No database access is permitted')
    monkeypatch.setattr('app.services.billing.get_connection', forbidden)
    body, signature = signed_event(livemode=kind == 'live', signed_at=int(time.time()) - 600 if kind == 'expired' else None)
    if kind == 'tampered': body += b' '
    if kind == 'missing': signature = ''
    with pytest.raises(HTTPException) as error:
        BillingService().webhook(body, signature)
    assert error.value.status_code == 400


def test_database_state_rolls_back_on_provider_error(monkeypatch):
    service, conn, _canonical = service_fixture(monkeypatch)
    service.gateway.request = lambda *_args: (_ for _ in ()).throw(HTTPException(502, 'fixture'))
    with pytest.raises(HTTPException): service.webhook(*signed_event())
    assert not conn.events and not conn.periods and conn.plan == 'trial'


def test_recovery_fetches_original_event_before_applying_paid_state(monkeypatch):
    service, conn, canonical = service_fixture(monkeypatch)
    body, _signature = signed_event(event_id='evt_recovery')
    event = json.loads(body)
    calls = []
    def request(method, path):
        calls.append((method, path))
        return event if path == 'events/evt_recovery' else canonical
    service.gateway.request = request
    service.recover_event('evt_recovery')
    assert calls[0] == ('GET', 'events/evt_recovery')
    assert conn.plan == 'pro' and len(conn.periods) == 1
    service.recover_event('evt_recovery')
    assert len(conn.periods) == 1


def test_recovery_rejects_arbitrary_paths_before_stripe_call(monkeypatch):
    service, conn, _canonical = service_fixture(monkeypatch)
    with pytest.raises(HTTPException): service.recover_event('evt_../customers')
    assert not service.gateway.calls and not conn.events


@pytest.mark.parametrize('path', ['/billing/status', '/billing/checkout', '/billing/checkout/fpx', '/billing/portal'])
def test_billing_routes_require_login(client, path):
    response = client.get(path) if path.endswith('status') else client.post(path)
    assert response.status_code == 401


def test_route_uses_authenticated_owner_not_submitted_identity(user_a_client):
    class Service:
        def checkout(self, user_id):
            assert user_id == 'user-a'
            return {'url': 'https://checkout.stripe.com/test_fixture'}
    app.dependency_overrides[get_billing_service] = lambda: Service()
    assert user_a_client.post('/billing/checkout', json={'user_id': 'user-b', 'price': 'price_other'}).status_code == 200


def test_missing_webhook_config_blocks_checkout(monkeypatch):
    monkeypatch.setattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    with pytest.raises(HTTPException) as error: BillingService().checkout('user-a')
    assert error.value.status_code == 503


def test_checkout_uses_server_price_owner_and_reuses_pending_session(monkeypatch):
    conn = MemoryConnection()
    price = {'id': 'price_fixture', 'active': True, 'livemode': False, 'currency': 'myr',
             'unit_amount': 5000, 'recurring': {'interval': 'month', 'interval_count': 1, 'usage_type': 'licensed'}}
    session = {'id': 'cs_fixture', 'url': 'https://checkout.stripe.com/fixture',
               'expires_at': int(time.time()) + 86400, 'status': 'open'}
    calls = []
    class Gateway:
        def request(self, method, path, data=None, idempotency_key=None):
            calls.append((method, path, data, idempotency_key))
            if path.startswith('prices/'): return price
            if path.startswith('subscriptions?'): return {'data': []}
            return session
    monkeypatch.setattr('app.services.billing.get_connection', lambda: conn)
    service = BillingService(Gateway())
    assert service.checkout('user-a') == {'url': session['url']}
    request = next(call for call in calls if call[:2] == ('POST', 'checkout/sessions'))
    assert request[2]['client_reference_id'] == 'user-a'
    assert request[2]['customer'] == 'cus_fixture'
    assert request[2]['line_items[0][price]'] == 'price_fixture'
    assert 'automatic_tax[enabled]' not in request[2]
    assert not any(key.startswith('payment_method_types') for key in request[2])
    assert service.checkout('user-a') == {'url': session['url']}
    assert sum(call[0] == 'POST' for call in calls) == 1


def test_existing_stripe_subscription_blocks_duplicate_purchase(monkeypatch):
    conn = MemoryConnection()
    price = {'id': 'price_fixture', 'active': True, 'livemode': False, 'currency': 'myr',
             'unit_amount': 5000, 'recurring': {'interval': 'month', 'interval_count': 1, 'usage_type': 'licensed'}}
    class Gateway:
        def request(self, method, path, *_args):
            assert method == 'GET'
            return price if path.startswith('prices/') else {'data': [{'status': 'active'}]}
    monkeypatch.setattr('app.services.billing.get_connection', lambda: conn)
    with pytest.raises(HTTPException) as error: BillingService(Gateway()).checkout('user-a')
    assert error.value.status_code == 409


@pytest.mark.parametrize('url', ['https://', 'http://untrusted.example', 'https://user:pass@example.com', 'https://example.com/?next=external'])
def test_unsafe_server_return_url_rejected(monkeypatch, url):
    monkeypatch.setattr(settings, 'STRIPE_RETURN_URL', url)
    with pytest.raises(HTTPException): BillingService.return_url()


@pytest.mark.parametrize('state', ['active', 'past_due', 'canceled', 'no_paid_invoice'])
def test_tracker_uses_paid_anniversary_snapshot_and_blocks_inactive(monkeypatch, state):
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(days=2), now + timedelta(days=28)
    rows = iter([('pro', now - timedelta(days=60)),
                 (None, None, None, 'active') if state == 'no_paid_invoice' else (start, end, Decimal('6.25'), state)])
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def execute(self, *_args): pass
        def fetchone(self): return next(rows)
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr('app.services.usage.tracker.get_connection', Conn)
    tracker = UsageTracker()
    tracker.ai_cost_used = lambda *_args: Decimal('0')
    if state == 'active':
        plan, actual_start, actual_end = tracker.period_for_user('user-a')
        assert plan.ai_budget_usd == Decimal('6.25')
        assert (actual_start, actual_end) == (start, end)
    else:
        with pytest.raises(HTTPException): tracker.ensure_ai_budget_available('user-a')


def test_exhausted_allowance_blocks_before_provider_call():
    tracker = UsageTracker()
    now = datetime.now(timezone.utc)
    tracker.period_for_user = lambda *_args: (get_plan_limits('pro'), now - timedelta(days=1), now + timedelta(days=1))
    tracker.ai_cost_used = lambda *_args: get_plan_limits('pro').ai_budget_usd
    with pytest.raises(HTTPException) as error: tracker.ensure_ai_budget_available('user-a')
    assert error.value.status_code == 429
