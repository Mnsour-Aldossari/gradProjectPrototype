import * as THREE from 'three'
import type { LatLon } from '../types'
import { tileLatLon, tileXY, toXY, type Frame } from './geo'

// The same imagery as the map (map/SurveyMap.tsx). It allows cross-origin use, so it can be a WebGL texture.
const TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const TILE_PX = 256
const MAX_TILES = 64
const SAND = '#c9b48a' // until the imagery loads, or if it cannot

/**
 * Satellite ground under the survey area and a margin around it: the map's tiles drawn into one canvas, laid on a
 * plane whose corners are the tiles' corners. Over a few hundred metres Web Mercator is straight to the millimetre.
 */
export function buildGround(frame: Frame, area: LatLon[], marginM: number): THREE.Mesh {
  const xs = area.map((p) => toXY(frame, p[0], p[1]))
  const minX = Math.min(...xs.map((p) => p[0])) - marginM
  const maxX = Math.max(...xs.map((p) => p[0])) + marginM
  const minY = Math.min(...xs.map((p) => p[1])) - marginM
  const maxY = Math.max(...xs.map((p) => p[1])) + marginM
  const latPerM = 1 / 111_195
  const lonPerM = latPerM / Math.cos((frame.lat0 * Math.PI) / 180)
  const north = frame.lat0 + maxY * latPerM
  const south = frame.lat0 + minY * latPerM
  const west = frame.lon0 + minX * lonPerM
  const east = frame.lon0 + maxX * lonPerM

  // The finest zoom (up to 19, the imagery's native one) that stays within MAX_TILES.
  let z = 19
  let range: { x0: number; x1: number; y0: number; y1: number }
  for (;;) {
    const [ax, ay] = tileXY(north, west, z)
    const [bx, by] = tileXY(south, east, z)
    range = { x0: Math.floor(ax), x1: Math.floor(bx), y0: Math.floor(ay), y1: Math.floor(by) }
    if ((range.x1 - range.x0 + 1) * (range.y1 - range.y0 + 1) <= MAX_TILES || z <= 15) break
    z--
  }
  const cols = range.x1 - range.x0 + 1
  const rows = range.y1 - range.y0 + 1

  const canvas = document.createElement('canvas')
  canvas.width = cols * TILE_PX
  canvas.height = rows * TILE_PX
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = SAND
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8

  for (let ty = range.y0; ty <= range.y1; ty++) {
    for (let tx = range.x0; tx <= range.x1; tx++) {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        ctx.drawImage(img, (tx - range.x0) * TILE_PX, (ty - range.y0) * TILE_PX)
        texture.needsUpdate = true
      }
      img.src = TILE_URL.replace('{z}', String(z)).replace('{y}', String(ty)).replace('{x}', String(tx))
    }
  }

  // The plane spans the tiles' corners, in the area's metres.
  const [nwLat, nwLon] = tileLatLon(range.x0, range.y0, z)
  const [seLat, seLon] = tileLatLon(range.x1 + 1, range.y1 + 1, z)
  const [x0, y0] = toXY(frame, nwLat, nwLon)
  const [x1, y1] = toXY(frame, seLat, seLon)
  const plane = new THREE.PlaneGeometry(x1 - x0, y0 - y1)
  const mesh = new THREE.Mesh(plane, new THREE.MeshLambertMaterial({ map: texture }))
  mesh.rotation.x = -Math.PI / 2
  mesh.position.set((x0 + x1) / 2, 0, -(y0 + y1) / 2)
  return mesh
}
