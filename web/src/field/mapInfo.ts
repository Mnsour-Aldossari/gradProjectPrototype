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

/** Same figure as the supervisor's Flight card: planned duration minus flight time so far. */
export function remainingS(mission: Mission, t: Telemetry | null): number {
  return mission.status === 'completed' ? 0 : Math.max(0, mission.estimated_duration_s - (t?.t_s ?? 0))
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
