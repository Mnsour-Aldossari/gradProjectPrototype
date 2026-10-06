import type { Detection, Mission, Telemetry } from '../types'

/** Figures for the cards on the field map, all derived from data the app already receives. */

/** A reported detection with its distance and compass direction from where the user stands. */
export interface Ranked {
  detection: Detection
  distance: number
  direction: string
}

/**
 * The survey flies lanes as pairs of waypoints, start and end (lawnmower_path in backend/app/simulation/flight.py),
 * so the waypoint being flown to gives the lane. Live telemetry carries it; a reloaded page waits for the next frame.
 */
export function laneProgress(mission: Mission, t: Telemetry | null): { lane: number | null; lanes: number } {
  const lanes = Math.floor((t?.waypoint_total ?? mission.path.length) / 2)
  if (mission.status === 'completed') return { lane: lanes, lanes }
  if (mission.status !== 'running' || t?.waypoint_seq === undefined) return { lane: null, lanes }
  return { lane: Math.min(lanes, Math.floor(t.waypoint_seq / 2) + 1), lanes }
}

/**
 * Time left in the survey, shared by the supervisor's Flight card and the field map. The simulator flies the planned
 * duration exactly. PX4 is slower than the plan (a stop at every lane end), so once it is under way the rest is
 * estimated from its own pace on the survey lines, timed from the first reading so takeoff does not count.
 */
export function remainingS(mission: Mission, t: Telemetry | null): number {
  if (mission.status === 'completed' || mission.status === 'stopped') return 0
  if (mission.phase === 'returning' || mission.phase === 'landing') return 0
  const elapsed = t?.t_s ?? 0
  const done = t?.progress ?? mission.progress
  if (mission.uav_source === 'px4' && done >= 0.05 && done < 1) {
    // Time spent paused does not count towards the pace.
    const surveying = elapsed - (t?.survey_start_s ?? 0) - (t?.paused_s ?? 0)
    return Math.max(0, (surveying * (1 - done)) / done)
  }
  return Math.max(0, mission.estimated_duration_s - elapsed)
}

/** Counts over the detections the field view reports (adaptive, not likely clutter). */
export function reportedCounts(reported: Detection[]): { high: number; suspect: number; verified: number; total: number } {
  return {
    high: reported.filter((d) => d.category === 'high').length,
    suspect: reported.filter((d) => d.category === 'suspect').length,
    verified: reported.filter((d) => d.status !== 'pending').length,
    total: reported.length,
  }
}
