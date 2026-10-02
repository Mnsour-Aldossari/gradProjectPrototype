// Map colours (SVG attributes cannot use CSS variables). They sit on satellite imagery, so they stay the same in the
// light and dark themes. Keep in sync with the light :root values in styles.css.
export const COLORS = {
  ink: '#1d2a24',
  hazard: '#c62d1f',
  amber: '#e0a526',
  survey: '#1f5fad',
  clutter: '#8a948c',
  white: '#ffffff',
} as const
