import { useLayoutEffect, useRef } from 'react'
import { formatDuration } from '../format'
import type { LiveState } from '../live'
import type { FitPadding } from '../map/SurveyMap'
import { usePrefs, type FieldPanel } from '../prefs'
import { COLORS } from '../theme'
import { CATEGORY_LABELS, SOIL_LABELS, STATUS_LABELS, VERIFICATION_LABELS, type Category, type Detection, type Mission, type Telemetry } from '../types'
import { formatDistance } from './geo'
import { laneProgress, remainingS, reportedCounts, type Ranked } from './mapInfo'

const PANEL_NAMES: Record<FieldPanel, string> = {
  mission: 'mission card',
  detections: 'detection counts',
  nearest: 'nearest detections',
  key: 'map key',
  drone: 'UAV status card',
}

// Cards at the top of the phone layout; the first one shown steps aside for the map's zoom buttons.
const TOP_PANELS: FieldPanel[] = ['mission', 'detections']

// Space kept around the survey area inside the part of the map the cards leave free.
const FIT_MARGIN = 12
const FIT_DEFAULT = 36

const LINK_LABELS: Record<LiveState['connection'], string> = {
  open: 'Live link',
  connecting: 'Reconnecting',
  closed: 'Reconnecting',
  failed: 'Link lost',
}

/** The map's marker shapes in miniature (same drawing as web/src/map/icons.ts), so the cards match the map. */
function MarkerGlyph({ category }: { category: Category }) {
  if (category === 'high')
    return (
      <svg className="hud-glyph" viewBox="0 0 30 30" aria-hidden="true">
        <path d="M15 2 L28.5 27 H1.5 Z" fill={COLORS.hazard} stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
        <rect x="13.6" y="10" width="2.8" height="9" rx="1.2" fill="#fff" />
        <circle cx="15" cy="22.6" r="1.7" fill="#fff" />
      </svg>
    )
  if (category === 'suspect')
    return (
      <svg className="hud-glyph" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 1.5 L22.5 12 L12 22.5 L1.5 12 Z" fill={COLORS.amber} stroke={COLORS.ink} strokeWidth="1.8" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="2.6" fill={COLORS.ink} />
      </svg>
    )
  return (
    <svg className="hud-glyph" viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="4.4" fill={COLORS.clutter} stroke="#fff" strokeWidth="1.4" />
    </svg>
  )
}

function UavGlyph() {
  return (
    <svg className="hud-glyph" viewBox="0 0 40 40" aria-hidden="true">
      <g stroke="#fff" strokeWidth="2.4">
        <line x1="9" y1="9" x2="31" y2="31" />
        <line x1="31" y1="9" x2="9" y2="31" />
      </g>
      <g fill={COLORS.survey} stroke="#fff" strokeWidth="1.6">
        <circle cx="9" cy="9" r="5.5" />
        <circle cx="31" cy="9" r="5.5" />
        <circle cx="9" cy="31" r="5.5" />
        <circle cx="31" cy="31" r="5.5" />
        <path d="M20 11 L26 25 L20 22 L14 25 Z" />
      </g>
    </svg>
  )
}

function HideButton({ panel }: { panel: FieldPanel }) {
  const { prefs, setPrefs } = usePrefs()
  return (
    <button
      type="button"
      className="hud-hide"
      aria-label={`Hide ${PANEL_NAMES[panel]}`}
      title="Hide"
      onClick={() => setPrefs({ fieldHidden: [...prefs.fieldHidden, panel] })}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <path d="M3 3l18 18 M10.6 5.1A9.8 9.8 0 0 1 12 5c5 0 9 4.5 10 7a12.7 12.7 0 0 1-3.2 4.2 M6.3 6.3C4.2 7.7 2.7 9.8 2 12c1 2.5 5 7 10 7a9.6 9.6 0 0 0 5.6-1.8 M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      </svg>
    </button>
  )
}

interface FieldMapInfoProps {
  mission: Mission
  telemetry: Telemetry | null
  connection: LiveState['connection']
  reported: Detection[]
  ranked: Ranked[]
  testLocation: boolean
  onOpen: (id: number) => void
  onSeeAll: () => void
  /** The space the visible cards cover along each edge of the map, for fitting the survey area. */
  onInsets: (insets: FitPadding) => void
}

/**
 * Cards over the field map (Map tab of /field): mission, detection counts, nearest detections, map key and the
 * UAV status card, each with its own hide button. Hidden cards are remembered per user (prefs.ts).
 */
export function FieldMapInfo({ mission, telemetry: t, connection, reported, ranked, testLocation, onOpen, onSeeAll, onInsets }: FieldMapInfoProps) {
  const { prefs, setPrefs } = usePrefs()
  const hidden = prefs.fieldHidden
  const shown = (panel: FieldPanel) => !hidden.includes(panel)
  const firstTop = TOP_PANELS.find(shown)
  const hudRef = useRef<HTMLDivElement>(null)
  const onInsetsRef = useRef(onInsets)

  useLayoutEffect(() => {
    onInsetsRef.current = onInsets
  }, [onInsets])

  // Measure what the cards cover. Which edge a card belongs to is set in CSS (--dock) for each screen layout.
  useLayoutEffect(() => {
    const hud = hudRef.current
    const area = hud?.parentElement
    if (!hud || !area) return
    let last = ''
    const measure = () => {
      const box = area.getBoundingClientRect()
      const edge = { top: 0, right: 0, bottom: 0, left: 0 }
      for (const el of hud.querySelectorAll<HTMLElement>('[data-dock]')) {
        const r = el.getBoundingClientRect()
        if (r.width === 0 || r.height === 0) continue
        const dock = getComputedStyle(el).getPropertyValue('--dock').trim()
        if (dock === 'top') edge.top = Math.max(edge.top, r.bottom - box.top)
        else if (dock === 'bottom') edge.bottom = Math.max(edge.bottom, box.bottom - r.top)
        else if (dock === 'left') edge.left = Math.max(edge.left, r.right - box.left)
        else if (dock === 'right') edge.right = Math.max(edge.right, box.right - r.left)
      }
      const pad = (covered: number) => Math.round(covered > 0 ? covered + FIT_MARGIN : FIT_DEFAULT)
      const insets = { top: pad(edge.top), right: pad(edge.right), bottom: pad(edge.bottom), left: pad(edge.left) }
      const key = `${insets.top},${insets.right},${insets.bottom},${insets.left}`
      if (key === last) return
      last = key
      onInsetsRef.current(insets)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(hud)
    for (const el of hud.querySelectorAll<HTMLElement>('[data-dock]')) observer.observe(el)
    return () => observer.disconnect()
  }, [hidden.join(','), testLocation])

  const progress = Math.round(mission.progress * 100)
  const { lane, lanes } = laneProgress(mission, t)
  const counts = reportedCounts(reported)
  const nearest = ranked[0]

  return (
    <div className="field-hud" ref={hudRef}>
      {(hidden.length > 0 || testLocation) && (
        <div className="hud-status" data-dock>
          {hidden.length > 0 && (
            <button type="button" className="hud-restore" onClick={() => setPrefs({ fieldHidden: [] })}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M2 12c1-2.5 5-7 10-7s9 4.5 10 7c-1 2.5-5 7-10 7S3 14.5 2 12z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              Show info ({hidden.length})
            </button>
          )}
          {testLocation && <span className="test-badge">Test location</span>}
        </div>
      )}

      {shown('mission') && (
        <section className={`hud-card hud-mission${firstTop === 'mission' ? ' hud-clear-zoom' : ''}`} data-dock aria-label="Mission">
          <div className="hud-head">
            <h2 className="hud-name">{mission.name}</h2>
            <HideButton panel="mission" />
          </div>
          <div className="hud-line">
            <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
            <span className="num">{progress}%</span>
            {lanes > 0 && <span>{lane === null ? `${lanes} lanes` : `Lane ${lane} of ${lanes}`}</span>}
            <span className="hud-narrow num">{formatDuration(remainingS(mission, t))} left</span>
          </div>
          <div className="progress dark" aria-hidden="true">
            <div style={{ width: `${progress}%` }} />
          </div>
          <dl className="hud-facts">
            <div className="hud-wide">
              <dt>Remaining</dt>
              <dd className="num">{formatDuration(remainingS(mission, t))}</dd>
            </div>
            <div>
              <dt>Flight time</dt>
              <dd className="num">{formatDuration(t?.t_s ?? 0)}</dd>
            </div>
            <div>
              <dt className="hud-wide">Speed</dt>
              <dd className="num">{t ? `${t.ground_speed_mps.toFixed(1)} m/s` : '–'}</dd>
            </div>
            <div>
              <dt className="hud-wide">Heading</dt>
              <dd className="num">{t ? `${Math.round(t.heading_deg)}°` : '–'}</dd>
            </div>
          </dl>
          <div className="hud-chips">
            <span className={`hud-chip hud-link-${connection}`}>
              <i aria-hidden="true" />
              {LINK_LABELS[connection]}
            </span>
            <span className="hud-chip">{SOIL_LABELS[mission.soil_type]}</span>
            <span className="hud-chip hud-sim">Simulated data</span>
          </div>
        </section>
      )}

      {shown('detections') && (
        <section className={`hud-card hud-detections${firstTop === 'detections' ? ' hud-clear-zoom' : ''}`} data-dock aria-label="Potential detections">
          <div className="hud-head">
            <h2 className="hud-title">Potential detections</h2>
            <HideButton panel="detections" />
          </div>
          <div className="hud-tiles">
            <div className="hud-tile hud-tile-high">
              <b className="num">{counts.high}</b>
              <span>
                <MarkerGlyph category="high" /> {CATEGORY_LABELS.high}
              </span>
            </div>
            <div className="hud-tile hud-tile-suspect">
              <b className="num">{counts.suspect}</b>
              <span>
                <MarkerGlyph category="suspect" /> {CATEGORY_LABELS.suspect}
              </span>
            </div>
            <div className="hud-tile">
              <b className="num">
                {counts.verified}
                <small> of {counts.total}</small>
              </b>
              <span>Verified</span>
            </div>
          </div>
        </section>
      )}

      {shown('nearest') && (
        <section className="hud-card hud-nearest" data-dock aria-label="Nearest potential detections">
          <div className="hud-head">
            <h2 className="hud-title">Nearest potential detections</h2>
            {ranked.length > 0 && (
              <button type="button" className="hud-more" onClick={onSeeAll}>
                See all
              </button>
            )}
            <HideButton panel="nearest" />
          </div>
          {ranked.length === 0 ? (
            <p className="hud-empty">Nothing reported yet.</p>
          ) : (
            <ul className="hud-near">
              {ranked.slice(0, 3).map((r) => (
                <li key={r.detection.id}>
                  <button type="button" onClick={() => onOpen(r.detection.id)}>
                    <span className="hud-near-id">
                      <MarkerGlyph category={r.detection.category} />#{r.detection.id}
                      <span className="hud-near-cat"> {CATEGORY_LABELS[r.detection.category]}</span>
                    </span>
                    <span className="hud-near-status">{VERIFICATION_LABELS[r.detection.status]}</span>
                    <span className="hud-near-dist num">
                      {formatDistance(r.distance)} <small>{r.direction}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {shown('key') && (
        <section className="hud-card hud-key" data-dock aria-label="Map key">
          <div className="hud-head">
            <h2 className="hud-title">Map key</h2>
            <HideButton panel="key" />
          </div>
          <ul className="hud-legend">
            <li>
              <MarkerGlyph category="high" /> {CATEGORY_LABELS.high}
            </li>
            <li>
              <MarkerGlyph category="suspect" /> {CATEGORY_LABELS.suspect}
            </li>
            <li>
              <i className={`hud-dot ${testLocation ? 'hud-dot-test' : 'hud-dot-you'}`} aria-hidden="true" />
              {testLocation ? 'Test location' : 'Your position'}
            </li>
            <li>
              <UavGlyph /> UAV
            </li>
            <li>
              <i className="hud-planned" aria-hidden="true" /> Planned path
            </li>
            <li>
              <i className="swatch swatch-swath" aria-hidden="true" /> Ground scanned
            </li>
            <li>
              <i className="hud-area" aria-hidden="true" /> Survey area
            </li>
          </ul>
          <ul className="hud-legend hud-layers" aria-label="Map layers">
            <li>
              <button
                type="button"
                className="hud-layer"
                aria-pressed={prefs.fieldLayers.labels}
                onClick={() => setPrefs({ fieldLayers: { ...prefs.fieldLayers, labels: !prefs.fieldLayers.labels } })}
              >
                <span className="hud-layer-sample">#6</span> Detection numbers
              </button>
            </li>
            <li>
              <button
                type="button"
                className="hud-layer"
                aria-pressed={prefs.fieldLayers.guide}
                onClick={() => setPrefs({ fieldLayers: { ...prefs.fieldLayers, guide: !prefs.fieldLayers.guide } })}
              >
                <i className="hud-guide" aria-hidden="true" /> Line to nearest
              </button>
            </li>
          </ul>
          <p className="hud-safety">Potential detections only. Do not enter the area based on this screen.</p>
        </section>
      )}

      {shown('drone') && (
        <section className="drone-card" data-dock aria-label="UAV status">
          <div className="drone-card-head">
            <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
            <span className="num">{progress}% of path</span>
            <HideButton panel="drone" />
          </div>
          <div className="progress dark" aria-hidden="true">
            <div style={{ width: `${progress}%` }} />
          </div>
          <dl>
            <div>
              <dt>Battery</dt>
              <dd className={`num${t && t.battery_pct < 25 ? ' warn' : ''}`}>{t ? `${t.battery_pct}%` : '–'}</dd>
            </div>
            <div>
              <dt>Height</dt>
              <dd className="num">{t ? `${t.relative_alt_m.toFixed(1)} m` : '–'}</dd>
            </div>
            <div>
              <dt>Nearest</dt>
              <dd className="num">{nearest ? `${formatDistance(nearest.distance)} ${nearest.direction}` : '–'}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  )
}
