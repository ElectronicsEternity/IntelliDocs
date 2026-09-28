import { useCallback, useEffect, useState } from 'react'

import type { IntelliDocsApi } from '../lib/api'
import type { UsageSummary } from '../types/api'

type Props = { api: IntelliDocsApi }

export function UsageBudgetBar({ api }: Props) {
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const refresh = useCallback(() => {
    api.getUsage().then(setUsage).catch(() => setUsage(null))
  }, [api])

  useEffect(() => {
    refresh()
    window.addEventListener('intellidocs:usage-updated', refresh)
    return () => window.removeEventListener('intellidocs:usage-updated', refresh)
  }, [refresh])

  if (!usage) return null
  const used = Math.min(100, Math.max(0, usage.ai_usage.used_percent))
  const remaining = Math.min(100, Math.max(0, usage.ai_usage.remaining_percent))
  return (
    <section className="account-usage-strip" aria-label="Account usage">
      <div className="account-usage-label">
        <strong>{Math.round(used)}% used</strong>
        <span>{Math.round(remaining)}% remaining</span>
      </div>
      <div aria-label={`${Math.round(used)}% of account usage allowance used`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={Math.round(used)} className="usage-bar" role="progressbar">
        <span className={used >= 90 ? 'near-limit' : ''} style={{ width: `${used}%` }} />
      </div>
    </section>
  )
}
