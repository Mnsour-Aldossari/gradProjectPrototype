import { PHASE_LABELS, STATUS_LABELS, type Mission } from '../types'

/** The mission's status, or while it flies what the UAV is doing after a supervisor's command (paused, returning). */
export function StatusBadge({ mission }: { mission: Mission }) {
  const phase = mission.status === 'running' && mission.phase && mission.phase !== 'surveying' ? mission.phase : null
  return phase ? (
    <span className={`status status-${phase}`}>{PHASE_LABELS[phase]}</span>
  ) : (
    <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
  )
}
