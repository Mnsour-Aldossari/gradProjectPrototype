// Map colours (SVG attributes cannot use CSS variables). Keep in sync with :root in styles.css.
export const COLORS = {
  ink: '#1d2a24',
  hazard: '#c62d1f',
  amber: '#e0a526',
  survey: '#1f5fad',
  clutter: '#8a948c',
  white: '#ffffff',
} as const

// Two-series chart palette, validated (lightness, chroma, colour-blind separation, contrast on #f6f8f4).
export const CHART = {
  baseline: '#b5651d',
  adaptive: '#1f5fad',
} as const
