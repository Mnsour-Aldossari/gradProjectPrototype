import { useState } from 'react'

export interface ChartGroup {
  key: string
  label: string
  baseline: number
  adaptive: number
}

// Colours are CSS variables (styles.css) so they follow the light/dark theme; SVG needs them in `style`, not attributes.
const SERIES = [
  { key: 'baseline' as const, label: 'Fixed threshold (baseline)', color: 'var(--series-baseline)' },
  { key: 'adaptive' as const, label: 'Adaptive', color: 'var(--series-adaptive)' },
]

function yScale(dataMax: number, isRatio: boolean): { yMax: number; ticks: number[] } {
  if (isRatio) return { yMax: 1, ticks: [0, 0.25, 0.5, 0.75, 1] }
  const step = dataMax <= 40 ? 10 : dataMax <= 100 ? 25 : 50
  const yMax = Math.max(step, Math.ceil(dataMax / step) * step)
  const ticks = []
  for (let v = 0; v <= yMax; v += step) ticks.push(v)
  return { yMax, ticks }
}

/** Grouped bars: one group per soil type, baseline and adaptive side by side, one y-axis. */
export function MetricChart({
  groups,
  isRatio,
  format,
  label,
}: {
  groups: ChartGroup[]
  isRatio: boolean
  format: (v: number) => string
  label: string
}) {
  const [hover, setHover] = useState<{ group: ChartGroup; series: (typeof SERIES)[number]; x: number; y: number } | null>(
    null,
  )
  const width = 640
  const height = 260
  const pad = { top: 16, right: 12, bottom: 34, left: 44 }
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom
  const dataMax = Math.max(...groups.flatMap((g) => [g.baseline, g.adaptive]), 1)
  const { yMax, ticks: allTicks } = yScale(dataMax, isRatio)
  const y = (v: number) => pad.top + plotH - (v / yMax) * plotH
  const groupW = plotW / groups.length
  const barW = Math.min(38, groupW * 0.28)
  const gap = 2

  return (
    <div className="chart">
      <div className="chart-legend" aria-hidden="true">
        {SERIES.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="chart-plot">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} by soil type for both methods; values are in the table below`}>
          {allTicks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className="chart-grid" />
              <text x={pad.left - 8} y={y(t)} className="chart-tick" textAnchor="end" dominantBaseline="middle">
                {isRatio ? t.toFixed(2) : t}
              </text>
            </g>
          ))}
          {groups.map((g, gi) => {
            const cx = pad.left + groupW * gi + groupW / 2
            return (
              <g key={g.key}>
                {SERIES.map((s, si) => {
                  const v = g[s.key]
                  const x = si === 0 ? cx - barW - gap / 2 : cx + gap / 2
                  const top = y(v)
                  const h = Math.max(0, y(0) - top)
                  const r = Math.min(4, h)
                  // Rounded data end at the top, square at the baseline.
                  const d = `M${x},${y(0)} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${y(0)} Z`
                  return (
                    <g key={s.key}>
                      <path d={d} style={{ fill: s.color }} />
                      {/* Hit target taller than the bar so short bars stay easy to hover */}
                      <rect
                        x={x - 1}
                        y={pad.top}
                        width={barW + 2}
                        height={plotH}
                        fill="transparent"
                        onMouseEnter={() => setHover({ group: g, series: s, x: x + barW / 2, y: top })}
                        onMouseLeave={() => setHover(null)}
                      />
                      {g.key === 'all' && (
                        <text x={x + barW / 2} y={top - 6} textAnchor="middle" className="chart-value">
                          {format(v)}
                        </text>
                      )}
                    </g>
                  )
                })}
                <text x={cx} y={height - 12} textAnchor="middle" className={`chart-cat${g.key === 'all' ? ' strong' : ''}`}>
                  {g.label}
                </text>
              </g>
            )
          })}
          <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} className="chart-axis" />
        </svg>
        {hover && (
          <div
            className="chart-tip"
            style={{ left: `${(hover.x / width) * 100}%`, top: `${(hover.y / height) * 100}%` }}
            role="status"
          >
            <strong>{hover.group.label}</strong>
            <span>
              <i style={{ background: hover.series.color }} />
              {hover.series.label}: {format(hover.group[hover.series.key])}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
