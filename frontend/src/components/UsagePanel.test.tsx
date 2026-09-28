import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { IntelliDocsApi } from '../lib/api'
import { UsagePanel } from './UsagePanel'

describe('UsagePanel', () => {
  it('shows the plan and all account allowances', async () => {
    const api = {
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
    expect(screen.getByText(/Questions use the same overall allowance/)).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})
