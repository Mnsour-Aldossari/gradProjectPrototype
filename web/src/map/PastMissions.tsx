import { useCallback, useEffect, useState } from 'react'
import { Polygon, Tooltip } from 'react-leaflet'
import { api } from '../api'
import { areaSize, formatDate } from '../format'
import { STATUS_LABELS, type Mission, type MissionStatus } from '../types'

/** Each status's colour on the map (bright, to read on satellite imagery). */
export const STATUS_MAP_COLORS: Record<MissionStatus, string> = {
  planned: '#c3cae0',
  running: '#3dd6f5',
  completed: '#34e3a0',
  stopped: '#ffb02e',
  failed: '#ff4d6d',
}

/** Every point of these missions' outlines, to fit the map to all of them. */
export function allPoints(missions: Mission[]) {
  return missions.flatMap((m) => m.area)
}

/**
 * Earlier missions drawn on a map: each outline in its status colour, with its name on hover. `selectedId` is drawn
 * brighter; `onSelect` makes the outlines clickable. Goes inside SurveyMap.
 */
export function PastMissions({
  missions,
  selectedId,
  onSelect,
  faint = false,
  inert = false,
}: {
  missions: Mission[]
  selectedId?: number | null
  onSelect?: (m: Mission) => void
  /** Drawn quietly, under an outline being planned. */
  faint?: boolean
  /** Not reacting to the pointer at all (while an outline is being drawn over them). */
  inert?: boolean
}) {
  return (
    <>
      {missions.map((m) => {
        const color = STATUS_MAP_COLORS[m.status]
        const selected = m.id === selectedId
        const size = areaSize(m.area)
        return (
          <Polygon
            key={`${m.id}:${selected}:${faint}:${inert}`}
            positions={m.area}
            interactive={!inert}
            eventHandlers={onSelect ? { click: () => onSelect(m) } : undefined}
            pathOptions={{
              color,
              weight: selected ? 3.5 : faint ? 1.6 : 2.4,
              opacity: faint && !selected ? 0.75 : 1,
              dashArray: selected ? undefined : '6 5',
              fillColor: color,
              fillOpacity: selected ? 0.28 : faint ? 0.08 : 0.16,
              className: `past-mission${selected ? ' is-selected' : ''}`,
            }}
          >
            {!inert && (
            <Tooltip sticky direction="top" className="past-tip" opacity={1}>
              <strong>{m.name}</strong>
              <span>
                {STATUS_LABELS[m.status]} · {size.width.toFixed(0)} × {size.height.toFixed(0)} m · {formatDate(m.created_at)}
              </span>
            </Tooltip>
            )}
          </Polygon>
        )
      })}
    </>
  )
}

const PAST_KEY = 'uav.map.past'

/**
 * The other missions, for a map to show behind the one in view: loaded once, hidden or shown with a button on the map
 * (remembered on this device). `exclude` is the mission the map is already about.
 */
export function usePastMissions(exclude?: number) {
  const [all, setAll] = useState<Mission[]>([])
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(PAST_KEY) !== 'off'
    } catch {
      return true
    }
  })
  useEffect(() => {
    let live = true
    api<Mission[]>('/api/missions')
      .then((list) => live && setAll(list))
      .catch(() => {
        // the earlier missions are an extra: without them the map is just the mission
      })
    return () => {
      live = false
    }
  }, [])
  const toggle = useCallback(() => {
    setOn((v) => {
      try {
        localStorage.setItem(PAST_KEY, v ? 'off' : 'on')
      } catch {
        // storage unavailable: the choice lasts until the page closes
      }
      return !v
    })
  }, [])
  const missions = all.filter((m) => m.id !== exclude && m.area.length >= 3)
  return { missions, on, toggle, past: { count: missions.length, on, onToggle: toggle } }
}

/** What the outline colours mean, under the overview map. */
export function PastKey() {
  return (
    <ul className="past-key" aria-label="Outline colours">
      {(Object.keys(STATUS_MAP_COLORS) as MissionStatus[]).map((s) => (
        <li key={s}>
          <i style={{ background: STATUS_MAP_COLORS[s] }} aria-hidden="true" />
          {STATUS_LABELS[s]}
        </li>
      ))}
    </ul>
  )
}
