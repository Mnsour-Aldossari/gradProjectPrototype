/** Flight poses along a stored track, for the live view and the replay of a finished survey. No three.js here. */

export interface Pose {
  t: number // flight time, s
  x: number // east, m
  y: number // north, m
  alt: number // height above ground, m
  heading: number // degrees, 0 = north, clockwise
  speed: number // m/s
  battery: number // %
  seq?: number // waypoint being flown to
}

/** Index of the last pose at or before t (0 if t is before the first). */
function indexAt(poses: Pose[], t: number): number {
  let lo = 0
  let hi = poses.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (poses[mid].t <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

function lerpAngle(a: number, b: number, u: number): number {
  const d = ((((b - a) % 360) + 540) % 360) - 180
  return (a + d * u + 360) % 360
}

/** The pose at flight time t, between the two stored poses around it. */
export function poseAt(poses: Pose[], t: number): Pose {
  const i = indexAt(poses, t)
  const a = poses[i]
  const b = poses[Math.min(i + 1, poses.length - 1)]
  const u = b.t > a.t ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 0
  return {
    t,
    x: a.x + (b.x - a.x) * u,
    y: a.y + (b.y - a.y) * u,
    alt: a.alt + (b.alt - a.alt) * u,
    heading: lerpAngle(a.heading, b.heading, u),
    speed: a.speed + (b.speed - a.speed) * u,
    battery: a.battery + (b.battery - a.battery) * u,
    seq: a.seq,
  }
}

/** Number of poses flown by time t, to draw the track up to there. */
export function countAt(poses: Pose[], t: number): number {
  return poses.length === 0 || t < poses[0].t ? 0 : indexAt(poses, t) + 1
}

/**
 * When the replay shows a detection: the first time the UAV passed within reach of it (half the lane spacing, where
 * its sensors saw the ground). Detections carry no flight time, so this stands in for it. Never before the first pose.
 */
export function revealTime(poses: Pose[], x: number, y: number, reachM: number): number {
  let nearest = 0
  let best = Infinity
  for (let i = 0; i < poses.length; i++) {
    const d = Math.hypot(poses[i].x - x, poses[i].y - y)
    if (d <= reachM) return poses[i].t
    if (d < best) {
      best = d
      nearest = i
    }
  }
  return poses.length ? poses[nearest].t : 0
}
