import L from 'leaflet'
import { COLORS } from '../theme'
import type { Category, Detection } from '../types'

// Shape and colour both encode the category, so markers stay distinguishable without colour.
const SHAPES: Record<Category, { size: number; svg: string }> = {
  high: {
    size: 30,
    svg: `<svg viewBox="0 0 30 30" aria-hidden="true">
      <path d="M15 2 L28.5 27 H1.5 Z" fill="${COLORS.hazard}" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/>
      <rect x="13.6" y="10" width="2.8" height="9" rx="1.2" fill="#fff"/><circle cx="15" cy="22.6" r="1.7" fill="#fff"/>
    </svg>`,
  },
  suspect: {
    size: 24,
    svg: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 1.5 L22.5 12 L12 22.5 L1.5 12 Z" fill="${COLORS.amber}" stroke="${COLORS.ink}" stroke-width="1.8" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="2.6" fill="${COLORS.ink}"/>
    </svg>`,
  },
  clutter: {
    size: 12,
    svg: `<svg viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="4.4" fill="${COLORS.clutter}" stroke="#fff" stroke-width="1.4"/>
    </svg>`,
  },
}

// A frame drawn around the spot: around an adaptive marker it means both methods flagged it;
// an empty frame is a place only the fixed-threshold baseline reported.
const BASELINE_SVG = `<svg viewBox="0 0 36 36" aria-hidden="true">
  <rect x="2.5" y="2.5" width="31" height="31" fill="none" stroke="#fff" stroke-width="4"/>
  <rect x="2.5" y="2.5" width="31" height="31" fill="none" stroke="${COLORS.ink}" stroke-width="2" stroke-dasharray="5 3"/>
</svg>`

export function detectionIcon(d: Detection, selected: boolean): L.DivIcon {
  if (d.method === 'baseline') {
    return L.divIcon({
      className: `det-icon det-baseline${selected ? ' is-selected' : ''}`,
      html: BASELINE_SVG,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    })
  }
  const shape = SHAPES[d.category]
  const verified = d.status !== 'pending' ? ` is-${d.status}` : ''
  return L.divIcon({
    className: `det-icon det-${d.category}${selected ? ' is-selected' : ''}${verified}`,
    html: shape.svg,
    iconSize: [shape.size, shape.size],
    iconAnchor: [shape.size / 2, d.category === 'high' ? shape.size * 0.6 : shape.size / 2],
  })
}

export function uavIcon(headingDeg: number): L.DivIcon {
  return L.divIcon({
    className: 'uav-icon',
    html: `<svg viewBox="0 0 40 40" style="transform: rotate(${headingDeg}deg)" aria-hidden="true">
      <g stroke="#fff" stroke-width="2.4">
        <line x1="9" y1="9" x2="31" y2="31"/><line x1="31" y1="9" x2="9" y2="31"/>
      </g>
      <g fill="${COLORS.survey}" stroke="#fff" stroke-width="1.6">
        <circle cx="9" cy="9" r="5.5"/><circle cx="31" cy="9" r="5.5"/>
        <circle cx="9" cy="31" r="5.5"/><circle cx="31" cy="31" r="5.5"/>
        <path d="M20 11 L26 25 L20 22 L14 25 Z"/>
      </g>
    </svg>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  })
}
