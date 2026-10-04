import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { IntelliDocsApi } from '../lib/api'
import { UsagePanel } from './UsagePanel'

describe('UsagePanel', () => {
  it('shows the plan and all account allowances', async () => {
    const api = {
      getBilling: vi.fn().mockResolvedValue({ enabled: false, sandbox: true, monthly_price_myr: 50, subscription_status: 'none', cancel_at_period_end: false, has_customer: false }),
      getUsage: vi.fn().mockResolvedValue({
        plan_code: 'trial',
        plan_name: 'Trial',
        period_start: '2026-09-01T00:00:00Z',
        period_end: '2026-10-01T00:00:00Z',
        documents: { used: 2, limit: 25 },
        storage_bytes: { used: 1048576, limit: 52428800 },
        pages_processed: { used: 20, limit: 500 },
        ai_usage: { used_percent: 12.5, remaining_percent: 87.5 },
      }),
    } as unknown as IntelliDocsApi

    render(<UsagePanel api={api} />)

    expect((await screen.findAllByText('Trial plan')).length).toBe(2)
    expect(screen.getByText('Documents')).toBeInTheDocument()
    expect(screen.getByText('Pages processed')).toBeInTheDocument()
    expect(screen.getByText('Your trial ends on 1 October 2026.')).toBeInTheDocument()
    expect(screen.queryByText(/separate question limit/)).not.toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })
  it.each([true, false])('shows the correct Pro period wording when cancellation is %s', async (cancelled) => {
    const api = {
      getBilling: vi.fn().mockResolvedValue({ enabled: true, sandbox: true, monthly_price_myr: 50,
        subscription_status: 'active', cancel_at_period_end: cancelled, has_customer: true }),
      getUsage: vi.fn().mockResolvedValue({ plan_code: 'pro', plan_name: 'Pro',
        period_end: '2026-11-04T14:45:24Z', documents: { used: 2, limit: 25 },
        storage_bytes: { used: 1048576, limit: 52428800 }, pages_processed: { used: 20, limit: 500 } }),
    } as unknown as IntelliDocsApi
    render(<UsagePanel api={api} />)
    expect(await screen.findByText(cancelled
      ? 'Your Pro access ends on 4 November 2026.'
      : 'Your current allowance resets on 4 November 2026.')).toBeInTheDocument()
  })
})
