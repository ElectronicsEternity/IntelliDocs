import { useEffect, useState } from 'react'

import type { IntelliDocsApi } from '../lib/api'
import type { BillingStatus } from '../types/api'

export function BillingPanel({ api, onStatus }: { api: IntelliDocsApi; onStatus?: (status: BillingStatus) => void }) {
  const [billing, setBilling] = useState<BillingStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    // Share the same subscription status with the usage summary so it cannot
    // promise an allowance reset when cancellation is already scheduled.
    api.getBilling().then(value => { if (active) { setBilling(value); onStatus?.(value) } })
      .catch(() => { if (active) setError('Unable to load subscription settings.') })
    return () => { active = false }
  }, [api, onStatus])

  async function openStripe(manage: boolean, fpx = false) {
    setBusy(true)
    setError('')
    try {
      const result = manage ? await api.manageSubscription() : fpx ? await api.startFpxCheckout() : await api.startCheckout()
      // Only navigate to Stripe-hosted pages, even if an unexpected URL is returned.
      const url = new URL(result.url)
      if (url.protocol !== 'https:' || !['checkout.stripe.com', 'billing.stripe.com'].includes(url.hostname)) {
        throw new Error('An invalid payment address was returned.')
      }
      window.location.assign(url.href)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to open Stripe.')
      setBusy(false)
    }
  }

  const returned = new URLSearchParams(window.location.search).get('billing')
  const passActive = billing?.subscription_status === 'pass_active'
  const existing = billing && !['none', 'canceled', 'incomplete_expired', 'pass_active', 'pass_expired'].includes(billing.subscription_status)
  // Use the verified paid-period date, not a date inferred from today's month.
  const endDate = billing?.period_end ? new Date(billing.period_end) : null
  const endLabel = endDate && !Number.isNaN(endDate.getTime())
    ? endDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : null
  return (
    <section className="plan-note" aria-label="Subscription">
      <div>
        <strong>IntelliDocs Pro{billing ? billing.access_type === 'fpx'
          ? ` — RM${billing.monthly_price_myr} one-month pass` : ` — RM${billing.monthly_price_myr}/month` : ''}</strong>
        <p>Monthly AI allowance.</p>
        {billing?.access_type === 'fpx' && <p>FPX one-month pass — manual renewal, no automatic payments.</p>}
        {passActive && endLabel && <p>Your Pro pass ends on {endLabel}. Renew after it ends.</p>}
        <details><summary>Plan details</summary><p>Unused allowance does not roll over.</p></details>
        {billing?.sandbox && <p>Sandbox testing only — no real payment.</p>}
        {billing?.payment_review && <p role="alert">Your bank payment needs review. Please contact support before making another payment.</p>}
        {returned === 'success' && <p>Checkout completed. Pro activates after Stripe confirms payment. Refresh to check your allowance.</p>}
        {returned === 'cancelled' && <p>Checkout cancelled. Your plan has not changed.</p>}
        {billing?.cancel_at_period_end && <p>{endLabel
          ? `Subscription ends on ${endLabel}. Pro remains active until then and will not renew.`
          : 'Your subscription will end at the close of the paid period and will not renew.'}</p>}
        {billing && !billing.enabled && <p>Payment setup is awaiting webhook configuration.</p>}
        {error && <p role="alert">{error}</p>}
      </div>
      <div>
        <button disabled={!billing?.enabled || busy || passActive} onClick={() => void openStripe(Boolean(existing))}>
          {busy ? 'Opening Stripe…' : passActive ? 'Pro pass active' : existing ? 'Manage subscription' : 'Upgrade to Pro'}
        </button>
        {!existing && !passActive && !billing?.payment_review && <>
          <button disabled={!billing?.fpx_enabled || busy} onClick={() => void openStripe(false, true)}>Pay with FPX — RM50 for one month</button>
          <p>One-month pass. Manual renewal.</p>
          {billing && !billing.fpx_enabled && <p>FPX setup is pending.</p>}
        </>}
        {billing?.has_customer && !existing && <button disabled={!billing.enabled || busy} onClick={() => void openStripe(true)}>Billing history</button>}
      </div>
    </section>
  )
}
