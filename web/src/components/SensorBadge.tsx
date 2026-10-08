import type { Mission, SensorCollection } from '../types'

const LABELS: Record<SensorCollection, string> = {
  complete: 'Complete',
  partial: 'Partial',
  failed: 'Failed',
  not_started: 'Not started',
}

/** "Partial (62%)", "Collecting" while the UAV flies, or "Not recorded" for missions flown before it was. */
export function sensorText(mission: Mission): string {
  if (mission.status === 'running') return 'Collecting'
  const collection = mission.sensor_collection
  if (collection === null) return 'Not recorded'
  const coverage = mission.sensor_coverage
  return (collection === 'complete' || collection === 'partial') && coverage !== null
    ? `${LABELS[collection]} (${Math.floor(coverage * 100)}%)`
    : LABELS[collection]
}

/**
 * The sensor collection, apart from the flight's status: a flight can end well with readings missing, and a sensor
 * that stops never stops the flight. `label` ("Sensors") names it next to the flight's status.
 */
export function SensorBadge({ mission, label }: { mission: Mission; label?: string }) {
  const kind = mission.status === 'running' ? 'collecting' : (mission.sensor_collection ?? 'unknown')
  const text = sensorText(mission)
  return (
    <span className={`sensors sensors-${kind}`} title={mission.sensor_note ?? undefined}>
      {label ? `${label}: ${text}` : text}
    </span>
  )
}

/** Why the collection is not complete, and how many readings were taken, for under the badges. */
export function SensorNote({ mission }: { mission: Mission }) {
  if (mission.status === 'planned' || mission.sensor_collection === null) return null
  const n = mission.sensor_reading_count
  const count = `${n.toLocaleString('en')} reading${n === 1 ? '' : 's'}${mission.status === 'running' ? ' so far' : ''}`
  return (
    <p className="small sensor-note">
      Sensors: {mission.status !== 'running' && mission.sensor_note ? `${mission.sensor_note}. ${count}.` : `${count}.`}
    </p>
  )
}
