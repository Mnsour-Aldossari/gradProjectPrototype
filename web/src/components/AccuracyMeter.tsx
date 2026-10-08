import type { AccuracyEstimate } from '../types'

const pct = (v: number) => `${Math.round(v * 100)}%`

const TEXT = {
  en: {
    found: 'Mines found',
    reports: 'Reports that are mines',
    lowMetal: 'Low-metal mines found',
    note: (fa: string, n: number) =>
      `About ${fa} false alarms per hectare. From ${n} simulated surveys per setting; not field performance.`,
  },
  ar: {
    found: 'الألغام المكتشفة',
    reports: 'البلاغات الصحيحة',
    lowMetal: 'الألغام قليلة المعدن المكتشفة',
    note: (fa: string, n: number) =>
      `حوالي ${fa} إنذار خاطئ لكل هكتار. من ${n} مسحًا محاكى لكل إعداد؛ ليست أداءً ميدانيًا.`,
  },
}

/**
 * The detector's expected accuracy with the chosen height, speed, lane spacing and soil, from simulated surveys
 * (GET /api/accuracy, or the outline check). Bars for the share of mines found and of reports that are mines.
 */
export function AccuracyMeter({
  estimate,
  compact = false,
  lang = 'en',
}: {
  estimate: AccuracyEstimate
  compact?: boolean
  lang?: 'en' | 'ar'
}) {
  const e = estimate
  const t = TEXT[lang]
  const rows = [
    { label: t.found, value: e.recall, extra: `± ${Math.round(e.recall_margin * 100)}` },
    { label: t.reports, value: e.precision, extra: '' },
    { label: t.lowMetal, value: e.low_metal_recall, extra: '' },
  ]
  return (
    <div className={`accuracy${compact ? ' is-compact' : ''}`}>
      <dl className="accuracy-bars">
        {rows.map((r) => (
          <div key={r.label} className="accuracy-row">
            <dt>{r.label}</dt>
            <dd>
              <span className="accuracy-bar" aria-hidden="true">
                <span style={{ width: pct(r.value) }} />
              </span>
              <span className="num" dir="ltr">
                {pct(r.value)}
                {r.extra && <small> {r.extra}</small>}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      <p className="small num">{t.note(e.false_alarms_per_ha.toFixed(1), e.surveys)}</p>
    </div>
  )
}
