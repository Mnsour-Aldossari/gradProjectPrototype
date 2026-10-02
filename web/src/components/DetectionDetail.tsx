import { useEffect, useState } from 'react'
import { api } from '../api'
import { formatCoord, formatDate } from '../format'
import { CATEGORY_LABELS, VERIFICATION_LABELS, type Detection, type VerificationStatus } from '../types'

function EvidenceBar({ label, value }: { label: string; value: number | undefined }) {
  if (value === undefined) return null
  const scale = 3 // bar spans 0..3x threshold
  const pct = Math.min(100, (value / scale) * 100)
  return (
    <div className="evidence">
      <div className="evidence-head">
        <span>{label}</span>
        <span className="num">{value.toFixed(2)}× threshold</span>
      </div>
      <div className="evidence-track" aria-hidden="true">
        <div className={`evidence-fill${value >= 1 ? ' over' : ''}`} style={{ width: `${pct}%` }} />
        <div className="evidence-mark" style={{ left: `${100 / scale}%` }} />
      </div>
    </div>
  )
}

const STATUS_ORDER: VerificationStatus[] = ['pending', 'confirmed_by_team', 'false_alarm']

/** Asks before an unsaved verification change is thrown away. */
export function confirmDiscard(): boolean {
  return window.confirm('Discard the unsaved verification change?')
}

export function DetectionDetail({
  detection,
  onClose,
  onUpdated,
  onDirtyChange,
}: {
  detection: Detection
  onClose: () => void
  onUpdated: (d: Detection) => void
  /** Told whether the form holds an unsaved change, so the page can ask before switching detections. */
  onDirtyChange?: (dirty: boolean) => void
}) {
  const [status, setStatus] = useState<VerificationStatus>(detection.status)
  const [notes, setNotes] = useState(detection.notes ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setStatus(detection.status)
    setNotes(detection.notes ?? '')
    setSaved(false)
    setError(null)
  }, [detection.id, detection.status, detection.notes])

  const dirty = status !== detection.status || notes.trim() !== (detection.notes ?? '')
  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange])

  const f = detection.features
  const isBaseline = detection.method === 'baseline'

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const updated = await api<Detection>(`/api/detections/${detection.id}`, {
        method: 'PATCH',
        body: { status, notes: notes.trim() || null },
      })
      onUpdated(updated)
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the verification')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="detail" aria-labelledby="detail-title">
      <button type="button" className="link-button" onClick={() => (!dirty || confirmDiscard()) && onClose()}>
        Back to mission
      </button>
      <h2 id="detail-title" className={`detail-title cat-${detection.category}`}>
        <span className={`swatch swatch-${isBaseline ? 'baseline' : detection.category}`} aria-hidden="true" />
        {CATEGORY_LABELS[detection.category]}
        <span className="detail-id">#{detection.id}</span>
      </h2>
      <p className="detail-method">
        {isBaseline ? 'Fixed-threshold baseline (shown for comparison)' : 'Adaptive classification'}
      </p>
      <p className="notice">
        Potential detection only. Trained personnel must verify this location before any conclusion is drawn.
      </p>

      <dl className="facts">
        <div>
          <dt>Position</dt>
          <dd className="num">
            {formatCoord(detection.lat)}, {formatCoord(detection.lon)}
          </dd>
        </div>
        <div>
          <dt>Estimated depth</dt>
          <dd className="num">{detection.est_depth_m === null ? 'No radar reflector' : `${(detection.est_depth_m * 100).toFixed(0)} cm`}</dd>
        </div>
        <div>
          <dt>Metal detector peak</dt>
          <dd className="num">{detection.peak_md.toFixed(3)}</dd>
        </div>
        <div>
          <dt>Radar peak</dt>
          <dd className="num">{detection.peak_gpr.toFixed(3)}</dd>
        </div>
        <div>
          <dt>Samples above threshold</dt>
          <dd className="num">{detection.n_hits}</dd>
        </div>
        <div>
          <dt>Ranking score</dt>
          <dd className="num">{detection.confidence.toFixed(2)}</dd>
        </div>
      </dl>

      {!isBaseline && (
        <div className="evidence-group">
          <h3>Sensor evidence against local thresholds</h3>
          <EvidenceBar label="Metal detector" value={f.md_evidence} />
          <EvidenceBar label="Radar" value={f.gpr_evidence} />
          {typeof f.body_ratio === 'number' && typeof f.body_ratio_min === 'number' && (
            <p className="small">
              Radar-to-metal ratio {f.body_ratio.toFixed(2)} (a solid body needs at least {f.body_ratio_min.toFixed(2)} in this soil)
            </p>
          )}
        </div>
      )}

      <h3>Why this classification</h3>
      <p className="explanation">{detection.explanation}</p>

      <h3>Verification</h3>
      <div className="segmented" role="radiogroup" aria-label="Verification status">
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={status === s}
            className={status === s ? 'is-on' : ''}
            onClick={() => {
              setStatus(s)
              setSaved(false)
            }}
          >
            {VERIFICATION_LABELS[s]}
          </button>
        ))}
      </div>
      <label className="field">
        <span>Field notes</span>
        <textarea value={notes} maxLength={500} rows={3} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" className="button" disabled={saving} onClick={save}>
          {saving ? 'Saving' : 'Save verification'}
        </button>
        {saved && <span className="ok">Verification saved</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {detection.verified_at && (
        <p className="small">
          {VERIFICATION_LABELS[detection.status]} on {formatDate(detection.verified_at)}
        </p>
      )}
    </section>
  )
}
