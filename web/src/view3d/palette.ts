/**
 * Colours of the 3D scene. The scene is always dark (a dim ground so the overlays read), so it takes the app's dark
 * theme values from styles.css (:root[data-theme='dark']); the panels over it follow the user's theme instead.
 */
export const SCENE = {
  sky: '#0b1220', // --paper (dark)
  groundNear: '#3a352c',
  groundFar: '#1b1a17',
  ink: '#e6eaf2', // --ink (dark)
  survey: '#6b9bff', // --survey (dark)
  surveyLight: '#a9c4ff',
  hazard: '#f97066', // --hazard (dark)
  amber: '#fdb022', // --amber (dark)
  clutter: '#94a3b8', // --clutter
  ok: '#32d583', // --ok (dark): the takeoff pad
  landing: '#a78bfa', // the landing pad (the map's L, lightened for the dark ground)
} as const
