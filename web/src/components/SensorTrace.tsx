function Trace({ values, label, colour }: { values: number[]; label: string; colour: string }) {
  const width = 280
  const height = 46
  const max = Math.max(0.05, ...values)
  const points = values
    .map((v, i) => `${((i / Math.max(1, values.length - 1)) * width).toFixed(1)},${(height - (v / max) * (height - 4) - 2).toFixed(1)}`)
    .join(' ')
  const current = values.length ? values[values.length - 1] : null
  return (
    <div className="trace">
      <div className="trace-head">
        <span>{label}</span>
        <span className="num">{current === null ? 'no data' : current.toFixed(3)}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={`${label} over the last 30 seconds`}>
        <line x1="0" y1={height - 1} x2={width} y2={height - 1} className="trace-axis" />
        {values.length > 1 && <polyline points={points} fill="none" stroke={colour} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  )
}

export function SensorTrace({ md, gpr }: { md: number[]; gpr: number[] }) {
  return (
    <div className="traces">
      <Trace values={md} label="Metal detector" colour="#1d2a24" />
      <Trace values={gpr} label="Ground-penetrating radar" colour="#1f5fad" />
    </div>
  )
}
