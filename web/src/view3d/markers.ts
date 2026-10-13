import * as THREE from 'three'
import type { Category } from '../types'
import { SCENE } from './palette'

const CATEGORY_COLORS: Record<Category, string> = { high: SCENE.hazard, suspect: SCENE.amber, clutter: SCENE.clutter }
const POP_S = 0.45
const BUFFER_M = 5 // safety buffer drawn around high-priority detections (display only)

export interface MarkerSpec {
  id: number
  x: number
  y: number
  category: Category
}

/** A hatched disc with a dashed rim: the safety buffer around a high-priority detection. */
function hatchTexture(color: string): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')!
  g.save()
  g.beginPath()
  g.arc(128, 128, 124, 0, Math.PI * 2)
  g.clip()
  g.fillStyle = color
  g.globalAlpha = 0.1
  g.fillRect(0, 0, 256, 256)
  g.globalAlpha = 0.45
  g.strokeStyle = color
  g.lineWidth = 4
  for (let k = -256; k < 512; k += 22) {
    g.beginPath()
    g.moveTo(k, 0)
    g.lineTo(k + 256 * Math.tan((35 * Math.PI) / 180), 256)
    g.stroke()
  }
  g.restore()
  g.globalAlpha = 0.75
  g.setLineDash([16, 12])
  g.lineWidth = 5
  g.strokeStyle = color
  g.beginPath()
  g.arc(128, 128, 124, 0, Math.PI * 2)
  g.stroke()
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

/** A soft round glow, for the selected detection's head. */
function glowTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grad.addColorStop(0, 'rgba(255,255,255,0.9)')
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 64, 64)
  return new THREE.CanvasTexture(c)
}

/**
 * The potential detections: a ring on the ground, a stem and a diamond head in the category's colour. The selected
 * one gets wider rings and a glow; high-priority ones a hatched safety buffer (a layer that can be turned off).
 */
export class Markers {
  readonly group = new THREE.Group()
  private readonly pins = new Map<number, { pin: THREE.Group; category: Category; born: number; selection: THREE.Group }>()
  private readonly heads = new Map<Category, THREE.MeshStandardMaterial>()
  private readonly fills = new Map<Category, THREE.MeshBasicMaterial>()
  private readonly rims = new Map<Category, THREE.MeshBasicMaterial>()
  private readonly stems = new Map<Category, THREE.MeshBasicMaterial>()
  private readonly head = new THREE.OctahedronGeometry(0.32)
  private readonly hit = new THREE.SphereGeometry(0.8, 8, 6) // a bigger target for clicks and taps
  private readonly stem = new THREE.CylinderGeometry(0.025, 0.025, 1.3, 6)
  private readonly disc = new THREE.CircleGeometry(0.55, 32)
  private readonly rim = new THREE.RingGeometry(0.5, 0.6, 40)
  private readonly wideRim = new THREE.RingGeometry(0.95, 1.02, 48)
  private readonly widerRim = new THREE.RingGeometry(1.35, 1.4, 56)
  private readonly bufferDisc = new THREE.CircleGeometry(BUFFER_M, 48)
  private readonly bufferMaterial = new THREE.MeshBasicMaterial({
    map: hatchTexture(SCENE.hazard),
    transparent: true,
    depthWrite: false,
  })
  private readonly glow = new THREE.SpriteMaterial({ map: glowTexture(), color: SCENE.hazard, transparent: true, depthWrite: false })
  private readonly hitMaterial = new THREE.MeshBasicMaterial({ visible: false })
  private selected: number | null = null
  private buffers = true

  private mat<M extends THREE.Material>(cache: Map<Category, M>, c: Category, make: (color: string) => M): M {
    let m = cache.get(c)
    if (!m) {
      m = make(CATEGORY_COLORS[c])
      cache.set(c, m)
    }
    return m
  }

  private build(s: MarkerSpec): { pin: THREE.Group; selection: THREE.Group } {
    const pin = new THREE.Group()
    pin.position.set(s.x, 0, -s.y)
    const flat = (m: THREE.Mesh, y: number) => {
      m.rotation.x = -Math.PI / 2
      m.position.y = y
      return m
    }
    const fill = flat(
      new THREE.Mesh(
        this.disc,
        this.mat(this.fills, s.category, (color) => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false })),
      ),
      0.04,
    )
    const rim = flat(
      new THREE.Mesh(
        this.rim,
        this.mat(this.rims, s.category, (color) => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, side: THREE.DoubleSide })),
      ),
      0.05,
    )
    const stem = new THREE.Mesh(
      this.stem,
      this.mat(this.stems, s.category, (color) => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.7 })),
    )
    stem.position.y = 0.65
    const head = new THREE.Mesh(
      this.head,
      this.mat(this.heads, s.category, (color) =>
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.35, roughness: 0.4, flatShading: true }),
      ),
    )
    head.position.y = 1.5
    head.userData.spin = true
    const hit = new THREE.Mesh(this.hit, this.hitMaterial)
    hit.position.y = 1.1
    hit.userData.detectionId = s.id
    pin.add(fill, rim, stem, head, hit)

    // Selection: two wider rings and a glow round the head.
    const selection = new THREE.Group()
    const rimMat = this.mat(this.rims, s.category, () => new THREE.MeshBasicMaterial())
    const r1 = flat(new THREE.Mesh(this.wideRim, rimMat), 0.05)
    const r2 = flat(new THREE.Mesh(this.widerRim, rimMat), 0.05)
    r2.scale.setScalar(1)
    const glow = new THREE.Sprite(this.glow.clone())
    ;(glow.material as THREE.SpriteMaterial).color.set(CATEGORY_COLORS[s.category])
    ;(glow.material as THREE.SpriteMaterial).opacity = 0.55
    glow.scale.setScalar(1.15)
    glow.position.y = 1.5
    selection.add(r1, r2, glow)
    selection.visible = false
    pin.add(selection)

    if (s.category === 'high') {
      const buffer = flat(new THREE.Mesh(this.bufferDisc, this.bufferMaterial), 0.025)
      buffer.userData.buffer = true
      buffer.visible = this.buffers
      pin.add(buffer)
    }
    return { pin, selection }
  }

  /** Shows exactly these markers. New ones pop up unless animate is false (first load, reduced motion). */
  set(specs: MarkerSpec[], now: number, animate: boolean) {
    const keep = new Set(specs.map((s) => s.id))
    for (const [id, p] of this.pins) {
      if (!keep.has(id)) {
        this.group.remove(p.pin)
        this.pins.delete(id)
      }
    }
    for (const s of specs) {
      const existing = this.pins.get(s.id)
      if (existing && existing.category === s.category) {
        existing.pin.position.set(s.x, 0, -s.y)
        continue
      }
      if (existing) this.group.remove(existing.pin)
      const { pin, selection } = this.build(s)
      this.group.add(pin)
      this.pins.set(s.id, { pin, category: s.category, born: animate && !existing ? now : -Infinity, selection })
    }
    this.select(this.selected)
  }

  select(id: number | null) {
    this.selected = id
    for (const [pid, p] of this.pins) p.selection.visible = pid === id
  }

  setBuffers(on: boolean) {
    this.buffers = on
    for (const p of this.pins.values()) p.pin.traverse((o) => o.userData.buffer && (o.visible = on))
  }

  /**
   * Pop-in of new markers, a slow turn of the heads and a pulse on the selected one. Seen from far away the pins grow
   * (true size up close) so they stay visible over the whole area; the safety buffer keeps its true size.
   */
  animate(now: number, camera: THREE.Camera, still: boolean) {
    for (const [id, p] of this.pins) {
      const u = Math.min(1, (now - p.born) / POP_S)
      const pop = u >= 1 ? 1 : 1 - Math.pow(1 - u, 3) * Math.cos(u * 6)
      const far = Math.min(6, Math.max(1, camera.position.distanceTo(p.pin.position) / 18))
      const s = Math.max(0.01, pop * far * (id === this.selected ? 1.25 : 1))
      for (const child of p.pin.children) {
        if (child.userData.buffer) continue
        child.scale.setScalar(s)
        if (child.userData.spin && !still) child.rotation.y = now * 0.8
      }
      if (id === this.selected && !still) {
        const k = 1 + 0.06 * Math.sin(now * 4)
        p.selection.children[1].scale.setScalar(k)
      }
    }
  }

  /** The detection under a ray, if any. */
  pick(raycaster: THREE.Raycaster): number | null {
    const hits = raycaster.intersectObjects(this.group.children, true)
    for (const h of hits) if (h.object.userData.detectionId !== undefined) return h.object.userData.detectionId
    return null
  }

  dispose() {
    for (const g of [this.head, this.hit, this.stem, this.disc, this.rim, this.wideRim, this.widerRim, this.bufferDisc]) g.dispose()
    for (const cache of [this.heads, this.fills, this.rims, this.stems]) for (const m of cache.values()) m.dispose()
    this.bufferMaterial.map?.dispose()
    this.bufferMaterial.dispose()
    this.glow.map?.dispose()
    this.glow.dispose()
    this.hitMaterial.dispose()
  }
}
