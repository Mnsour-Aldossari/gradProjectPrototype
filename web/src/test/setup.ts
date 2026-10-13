/**
 * Runs before every test file (vitest.config.ts). jsdom is a browser without layout or graphics, so:
 * - the Leaflet map is replaced by a plain element that shows what the page gives it (where the UAV is, which
 *   detections), and drawing an outline by buttons that finish a known shape (src/test/fixtures.ts);
 * - the few browser features jsdom lacks are stubbed;
 * - each test starts signed out, with empty storage and no faked fetch or WebSocket left over.
 */
import { cleanup } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, vi } from 'vitest'
import type { Detection, Telemetry } from '../types'

vi.mock('../map/SurveyMap', async () => {
  const { createElement } = await import('react')
  return {
    SurveyMap: ({ uav, detections, children }: { uav?: Telemetry | null; detections?: Detection[]; children?: ReactNode }) =>
      createElement(
        'div',
        {
          'data-testid': 'survey-map',
          'data-uav': uav ? `${uav.lat},${uav.lon}` : '',
          'data-detections': (detections ?? []).map((d) => d.id).join(','),
        },
        children,
      ),
  }
})

vi.mock('../map/AreaEditor', async (importOriginal) => {
  const real = await importOriginal<typeof import('../map/AreaEditor')>()
  const { createElement } = await import('react')
  const { TEST_SHAPES } = await import('./fixtures')
  return {
    ...real,
    AreaHandles: () => null,
    AreaDrawer: ({ onDone }: { onDone: (shape: { kind: 'polygon'; points: [number, number][] }) => void }) =>
      createElement(
        'div',
        null,
        Object.entries(TEST_SHAPES).map(([name, points]) =>
          createElement(
            'button',
            { key: name, type: 'button', onClick: () => onDone({ kind: 'polygon', points }) },
            `Finish drawing: ${name}`,
          ),
        ),
      ),
  }
})

vi.mock('../map/TakeoffPoint', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../map/TakeoffPoint')>()),
  TakeoffPoint: () => null,
}))

// Map layers a page puts inside the map need Leaflet's map; the map is a plain element here.
vi.mock('react-leaflet', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-leaflet')>()),
  Circle: () => null,
  CircleMarker: () => null,
  Marker: () => null,
  Polygon: () => null,
  Polyline: () => null,
  Tooltip: () => null,
}))

window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }) as MediaQueryList

if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute('open')) return
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}

Element.prototype.scrollTo ??= () => undefined
Element.prototype.scrollIntoView ??= () => undefined

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
  delete document.documentElement.dataset.theme
  delete document.documentElement.dataset.font
  delete document.documentElement.dataset.density
})
