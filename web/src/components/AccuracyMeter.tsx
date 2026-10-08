import type { AccuracyEstimate } from '../types'

const pct = (v: number) => `${Math.round(v * 100)}%`

/**
 * The detector's expected accuracy with the chosen height, speed, lane spacing and soil, from simulated surveys
 * (GET /api/accuracy, or the outline check). Bars for the share of mines found and of reports that are mines.
 */
export function AccuracyMeter({ estimate, compact = false }: { estimate: AccuracyEstimate; compact?: boolean }) {
  const e = estimate
  const rows = [
    { label: 'Mines found', value: e.recall, extra: `± ${Math.round(e.recall_margin * 100)}` },
    { label: 'Reports that are mines', value: e.precision, extra: '' },
    { label: 'Low-metal mines found', value: e.low_metal_recall, extra: '' },
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
              <span className="num">
                {pct(r.value)}
                {r.extra && <small> {r.extra}</small>}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      <p className="small num">
        About {e.false_alarms_per_ha.toFixed(1)} false alarms per hectare. From {e.surveys} simulated surveys per
        setting; not field performance.
      </p>
    </div>
  )
}
