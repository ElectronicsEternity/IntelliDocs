import { useEffect, useState } from 'react'

import type { IntelliDocsApi } from '../lib/api'
import type { UsageMetric, UsageSummary } from '../types/api'

type Props = { api: IntelliDocsApi }

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function UsageCard({ label, metric, format = String, monthly = false }: {
  label: string
  metric: UsageMetric
  format?: (value: number) => string
  monthly?: boolean
}) {
  const percentage = metric.limit > 0 ? Math.min(100, Math.round(metric.used / metric.limit * 100)) : 0
  return (
    <article className="usage-card">
      <div className="usage-card-heading">
        <h3>{label}</h3>
        {monthly && <span>this month</span>}
      </div>
      <p className="usage-value"><strong>{format(metric.used)}</strong> of {format(metric.limit)}</p>
      <div aria-label={`${label}: ${percentage}% used`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={percentage} className="usage-bar" role="progressbar">
        <span className={percentage >= 90 ? 'near-limit' : ''} style={{ width: `${percentage}%` }} />
      </div>
      <p className="usage-remaining">{format(Math.max(0, metric.limit - metric.used))} remaining</p>
    </article>
  )
}

export function UsagePanel({ api }: Props) {
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.getUsage()
      .then((value) => { if (active) setUsage(value) })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to load usage.') })
    return () => { active = false }
  }, [api])

  if (error) return <p className="notice notice-error">{error}</p>
  if (!usage) return <div className="inline-loader"><div className="loader" /><p>Loading account usage…</p></div>

  const resetDate = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(usage.period_end))
  return (
    <section aria-labelledby="usage-heading">
      <div className="section-heading usage-heading">
        <div>
          <p className="eyebrow">Account and allowances</p>
          <h2 id="usage-heading">Usage</h2>
          <p className="muted">See how much of your IntelliDocs allowance you have used.</p>
        </div>
        <span className={`plan-badge plan-${usage.plan_code}`}>{usage.plan_name} plan</span>
      </div>
      <div className="usage-grid">
        <UsageCard label="Documents" metric={usage.documents} />
        <UsageCard format={formatBytes} label="Storage" metric={usage.storage_bytes} />
        <UsageCard label="Pages processed" metric={usage.pages_processed} monthly />
        <UsageCard label="Questions asked" metric={usage.questions} monthly />
      </div>
      <div className="plan-note">
        <div><strong>{usage.plan_name} plan</strong><p>Monthly page and question allowances reset on {resetDate}.</p></div>
        {usage.plan_code === 'trial' && <span>Pro upgrades and payments are coming in a later change set.</span>}
      </div>
    </section>
  )
}
