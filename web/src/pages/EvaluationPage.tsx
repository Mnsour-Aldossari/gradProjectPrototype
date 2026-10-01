import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { MetricChart, type ChartGroup } from '../components/MetricChart'
import type { EvaluationCounts, EvaluationReport } from '../types'

type Metric = 'f1' | 'recall' | 'precision' | 'fp'

const METRICS: { key: Metric; label: string; ratio: boolean }[] = [
  { key: 'f1', label: 'F1', ratio: true },
  { key: 'recall', label: 'Recall', ratio: true },
  { key: 'precision', label: 'Precision', ratio: true },
  { key: 'fp', label: 'False alarms', ratio: false },
]

const METHOD_LABELS = { baseline: 'Fixed threshold (baseline)', adaptive: 'Adaptive' } as const

function value(c: EvaluationCounts, m: Metric): number {
  return c[m]
}

export function EvaluationPage() {
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [metric, setMetric] = useState<Metric>('f1')

  useEffect(() => {
    api<EvaluationReport>('/api/evaluation')
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the evaluation'))
  }, [])

  const current = METRICS.find((m) => m.key === metric)!
  const groups = useMemo<ChartGroup[]>(
    () =>
      report?.soils.map((s) => ({
        key: s.key,
        label: s.label.replace('Mineralised rocky soil', 'Mineralised rocky'),
        baseline: value(report.results.baseline[s.key], metric),
        adaptive: value(report.results.adaptive[s.key], metric),
      })) ?? [],
    [report, metric],
  )

  return (
    <main className="page evaluation">
      <h1>Evaluation: adaptive classification vs. a fixed threshold</h1>

      <div className="simulated-banner" role="note">
        <p lang="ar" dir="rtl" className="ar">
          النتائج على بيانات محاكاة
        </p>
        <p>{report?.notice ?? 'Results on simulated data.'}</p>
      </div>

      {error && <p className="error">{error}</p>}
      {!report && !error && (
        <p className="small">Running both methods on 90 simulated surveys. This takes a few seconds the first time.</p>
      )}

      {report && (
        <>
          <p className="lede">
            {report.protocol.scenarios} simulated surveys (evaluation seeds {report.protocol.evaluation_seeds[0]}–
            {report.protocol.evaluation_seeds[1]}, three soil types). All parameters were frozen on separate tuning seeds
            before this run. A detection counts as found when a reported marker lies within{' '}
            {report.protocol.match_radius_m} m of a buried mine; anything else reported is a false alarm.
          </p>

          <section className="eval-section" aria-labelledby="chart-heading">
            <div className="row spread">
              <h2 id="chart-heading">{current.label} by soil type</h2>
              <div className="segmented compact" role="radiogroup" aria-label="Metric">
                {METRICS.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    role="radio"
                    aria-checked={metric === m.key}
                    className={metric === m.key ? 'is-on' : ''}
                    onClick={() => setMetric(m.key)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            <MetricChart
              groups={groups}
              isRatio={current.ratio}
              label={current.label}
              format={(v) => (current.ratio ? v.toFixed(2) : String(v))}
            />
            <p className="small">
              {metric === 'fp' ? 'Lower is better.' : 'Higher is better.'} Hover a bar for its value; all values are in
              the table.
            </p>
          </section>

          <section className="eval-section" aria-labelledby="table-heading">
            <h2 id="table-heading">Results table</h2>
            <div className="table-scroll">
              <table className="table num-table">
                <thead>
                  <tr>
                    <th>Soil</th>
                    <th>Method</th>
                    <th>Mines found</th>
                    <th>Recall</th>
                    <th>Precision</th>
                    <th>F1</th>
                    <th>False alarms</th>
                  </tr>
                </thead>
                <tbody>
                  {report.soils.map((s) =>
                    (['baseline', 'adaptive'] as const).map((m, i) => {
                      const r = report.results[m][s.key]
                      return (
                        <tr key={`${s.key}-${m}`} className={s.key === 'all' ? 'total' : ''}>
                          {i === 0 && <th rowSpan={2}>{s.label}</th>}
                          <td>
                            <i className={`series-dot ${m}`} aria-hidden="true" />
                            {METHOD_LABELS[m]}
                          </td>
                          <td className="num">
                            {r.tp} of {r.targets}
                          </td>
                          <td className="num">{r.recall.toFixed(3)}</td>
                          <td className="num">{r.precision.toFixed(3)}</td>
                          <td className="num">{r.f1.toFixed(3)}</td>
                          <td className="num">{r.fp}</td>
                        </tr>
                      )
                    }),
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="eval-section limitations" aria-labelledby="limits-heading">
            <h2 id="limits-heading">
              Known limitations{' '}
              <span lang="ar" dir="rtl" className="ar">
                حدود معروفة
              </span>
            </h2>
            <ul>
              {report.limitations.map((l) => (
                <li key={l.title}>
                  <strong>{l.title}.</strong> {l.text}
                </li>
              ))}
            </ul>
            <table className="table compact-table">
              <caption>{report.borderline_case.description}</caption>
              <tbody>
                {report.borderline_case.seeds.map((b) => (
                  <tr key={b.seed}>
                    <th className="num">Seed {b.seed}</th>
                    <td className={b.reported ? 'ok' : 'miss'}>{b.reported ? 'Reported' : 'Missed'}</td>
                    <td>{b.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="eval-section" aria-labelledby="tests-heading">
            <h2 id="tests-heading">Pass criteria fixed before the evaluation</h2>
            <table className="table">
              <tbody>
                {report.mandatory_tests.map((t) => (
                  <tr key={t.id}>
                    <th>{t.id}</th>
                    <td>{t.name}</td>
                    <td className="num">{t.value}</td>
                    <td className={t.passed ? 'ok' : 'miss'}>{t.passed ? 'Pass' : 'Fail'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="eval-section" aria-labelledby="params-heading">
            <h2 id="params-heading">Frozen parameters</h2>
            <p className="small">
              Baseline: one metal-detector threshold of {report.frozen_parameters.baseline.md_threshold} for every soil.
              Adaptive: k<sub>md</sub> {report.frozen_parameters.adaptive.k_md}, k<sub>gpr</sub>{' '}
              {report.frozen_parameters.adaptive.k_gpr}, body ratio {report.frozen_parameters.adaptive.body_ratio}, with
              per-soil reliabilities. Seeds, calibration and the full protocol are in docs/EVALUATION_PROTOCOL.md.
            </p>
          </section>
        </>
      )}
    </main>
  )
}
