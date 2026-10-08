import type { Detection, LatLon, Mission, Telemetry, User } from '../types'

export const SUPERVISOR: User = { id: 1, username: 'supervisor', full_name: 'Mission Supervisor', role: 'supervisor' }
export const FIELD_OPERATOR: User = { id: 2, username: 'field', full_name: 'Field Operator', role: 'field_operator' }

// The 60 m x 40 m test field near Al-Kharj, as on the new mission page.
export const TEST_FIELD: LatLon[] = [
  [24.13968, 47.2617],
  [24.13968, 47.2623],
  [24.13932, 47.2623],
  [24.13932, 47.2617],
]

/** Outlines the faked drawing tool can finish with (setup.ts): one fine, one too small. */
export const TEST_SHAPES: Record<string, LatLon[]> = {
  '30 m square': [
    [24.14, 47.26],
    [24.14, 47.2603],
    [24.13973, 47.2603],
    [24.13973, 47.26],
  ],
  '1 m square': [
    [24.14, 47.26],
    [24.14, 47.26001],
    [24.139991, 47.26001],
    [24.139991, 47.26],
  ],
}

export function mission(overrides: Partial<Mission> = {}): Mission {
  return {
    id: 1,
    name: 'Test field survey',
    area: TEST_FIELD,
    path: [TEST_FIELD[0], TEST_FIELD[1]],
    path_length_m: 600,
    altitude_m: 1.5,
    speed_mps: 2,
    line_spacing_m: 2,
    soil_type: 'dry_sand',
    scenario_seed: 7,
    status: 'running',
    uav_source: 'simulated',
    takeoff_lat: null,
    takeoff_lon: null,
    landing_lat: null,
    landing_lon: null,
    progress: 0.1,
    battery_pct: 98,
    error: null,
    created_by: 1,
    created_at: '2026-10-08T08:00:00Z',
    started_at: '2026-10-08T08:01:00Z',
    completed_at: null,
    estimated_duration_s: 300,
    phase: 'surveying',
    ...overrides,
  }
}

export function detection(overrides: Partial<Detection> = {}): Detection {
  return {
    id: 7,
    mission_id: 1,
    method: 'adaptive',
    lat: 24.1395,
    lon: 47.262,
    category: 'high',
    category_label: 'High priority',
    confidence: 0.86,
    peak_md: 0.42,
    peak_gpr: 0.31,
    est_depth_m: 0.12,
    n_hits: 5,
    explanation: 'Metal and radar both above their local thresholds.',
    features: { md_evidence: 2.1, gpr_evidence: 1.6 },
    status: 'pending',
    notes: null,
    verified_by: null,
    verified_at: null,
    created_at: '2026-10-08T08:02:00Z',
    ...overrides,
  }
}

export function telemetry(overrides: Partial<Telemetry> = {}): Telemetry {
  return {
    t_s: 12,
    lat: 24.13965,
    lon: 47.2618,
    relative_alt_m: 1.5,
    heading_deg: 90,
    ground_speed_mps: 2,
    battery_pct: 97,
    progress: 0.2,
    md: 0.05,
    gpr: 0.02,
    ...overrides,
  }
}
