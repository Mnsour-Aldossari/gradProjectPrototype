export type Role = 'supervisor' | 'field_operator'
export type MissionStatus = 'planned' | 'running' | 'completed' | 'failed'
export type SoilType = 'dry_sand' | 'wet_clay' | 'mineralized_rocky'
export type Category = 'high' | 'suspect' | 'clutter'
export type VerificationStatus = 'pending' | 'confirmed_by_team' | 'false_alarm'
export type LatLon = [number, number]

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
}

export interface MissionStats {
  telemetry_points: number
  sensor_readings: number
  detections: number
}

export interface Mission {
  id: number
  name: string
  area: LatLon[]
  path: LatLon[]
  path_length_m: number
  altitude_m: number
  speed_mps: number
  line_spacing_m: number
  soil_type: SoilType
  scenario_seed: number
  status: MissionStatus
  progress: number
  battery_pct: number | null
  error: string | null
  created_by: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  estimated_duration_s: number
  stats?: MissionStats | null
}

export interface DetectionFeatures {
  reason?: string
  md_evidence?: number
  gpr_evidence?: number
  body_ratio?: number | null
  body_ratio_min?: number
  md_threshold_k?: number
  gpr_threshold_k?: number
  md_threshold?: number
  [key: string]: unknown
}

export interface Detection {
  id: number
  mission_id: number
  method: 'adaptive' | 'baseline'
  lat: number
  lon: number
  category: Category
  category_label: string
  confidence: number
  peak_md: number
  peak_gpr: number
  est_depth_m: number | null
  n_hits: number
  explanation: string
  features: DetectionFeatures
  status: VerificationStatus
  notes: string | null
  verified_by: number | null
  verified_at: string | null
  created_at: string
}

export interface Telemetry {
  t_s: number
  lat: number
  lon: number
  relative_alt_m: number
  heading_deg: number
  ground_speed_mps: number
  battery_pct: number
  waypoint_seq?: number
  waypoint_total?: number
  progress?: number
  md?: number | null
  gpr?: number | null
}

export interface ConditionProfile {
  soil_type: SoilType
  soil_label: string
  permittivity: number
  md_reliability: number
  gpr_reliability: number
  md_threshold_k: number
  gpr_threshold_k: number
  radar_trusted: boolean
  background_window_m: number
  link_radius_m: number
  notes: string[]
}

export const SOIL_LABELS: Record<SoilType, string> = {
  dry_sand: 'Dry sand',
  wet_clay: 'Wet clay',
  mineralized_rocky: 'Mineralised rocky soil',
}

export const CATEGORY_LABELS: Record<Category, string> = {
  high: 'High priority',
  suspect: 'Needs verification',
  clutter: 'Likely clutter',
}

export const STATUS_LABELS: Record<MissionStatus, string> = {
  planned: 'Planned',
  running: 'Surveying',
  completed: 'Completed',
  failed: 'Failed',
}

export const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  pending: 'Awaiting verification',
  confirmed_by_team: 'Confirmed by team',
  false_alarm: 'False alarm',
}
