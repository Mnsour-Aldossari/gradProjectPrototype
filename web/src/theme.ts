// Map colours (SVG attributes cannot use CSS variables). They sit on satellite imagery, so they stay the same in the
// light and dark themes. Brighter than the cards' palette (styles.css) so they read on imagery.
export const COLORS = {
  ink: '#1d2a24',
  hazard: '#ff3b5c',
  amber: '#ffb02e',
  survey: '#22b8f0',
  clutter: '#8a948c',
  white: '#ffffff',
} as const
