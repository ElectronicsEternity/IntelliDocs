import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { IntelliDocsApi } from '../lib/api'
import { BillingPanel } from './BillingPanel'

function mockApi(subscription_status = 'none', enabled = true) {
  return {
    getBilling: vi.fn().mockResolvedValue({ enabled, sandbox: true, monthly_price_myr: 50,
      subscription_status, cancel_at_period_end: false, period_end: null as string | null,
      has_customer: subscription_status !== 'none' }),
    startCheckout: vi.fn().mockRejectedValue(new Error('Fixture checkout error')),
    startFpxCheckout: vi.fn().mockRejectedValue(new Error('Fixture FPX error')),
    manageSubscription: vi.fn().mockRejectedValue(new Error('Fixture portal error')),
  }
}

describe('BillingPanel', () => {
  it('opens the FPX checkout separately from card subscription', async () => {
    const api = mockApi()
    api.getBilling.mockResolvedValueOnce({ enabled: true, sandbox: true, monthly_price_myr: 50,
      subscription_status: 'none', cancel_at_period_end: false, has_customer: false,
      period_end: null, fpx_enabled: true })
    render(<BillingPanel api={api as unknown as IntelliDocsApi} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Pay with FPX — RM50 for one month' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fixture FPX error')
    expect(api.startFpxCheckout).toHaveBeenCalledOnce()
    expect(api.startCheckout).not.toHaveBeenCalled()
  })
  it('shows the cancellation date while keeping subscription management available', async () => {
    const api = mockApi('active')
    api.getBilling.mockResolvedValueOnce({ enabled: true, sandbox: true, monthly_price_myr: 50,
      subscription_status: 'active', cancel_at_period_end: true, has_customer: true,
      period_end: '2026-11-04T14:45:24Z' })
    render(<BillingPanel api={api as unknown as IntelliDocsApi} />)
    expect(await screen.findByText(/Subscription ends on 4 November 2026/)).toHaveTextContent('will not renew')
    expect(screen.getByRole('button', { name: 'Manage subscription' })).toBeEnabled()
  })
  it('shows sandbox price and blocks checkout until webhooks are configured', async () => {
    render(<BillingPanel api={mockApi('none', false) as unknown as IntelliDocsApi} />)
    expect(await screen.findByText('IntelliDocs Pro — RM50/month')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upgrade to Pro' })).toBeDisabled()
    expect(screen.getByText(/no real payment/)).toBeInTheDocument()
  })
  it('starts checkout and shows safe provider errors', async () => {
    const api = mockApi()
    render(<BillingPanel api={api as unknown as IntelliDocsApi} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Upgrade to Pro' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fixture checkout error')
    expect(api.startCheckout).toHaveBeenCalledOnce()
  })
  it('offers the portal for an existing subscription', async () => {
    const api = mockApi('past_due')
    render(<BillingPanel api={api as unknown as IntelliDocsApi} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Manage subscription' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fixture portal error')
    expect(api.manageSubscription).toHaveBeenCalledOnce()
  })
})
