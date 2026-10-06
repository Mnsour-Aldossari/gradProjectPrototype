import * as THREE from 'three'
import { COLORS } from '../theme'
import type { Category } from '../types'

const CATEGORY_COLORS: Record<Category, string> = { high: COLORS.hazard, suspect: COLORS.amber, clutter: COLORS.clutter }
const POP_S = 0.45

export interface MarkerSpec {
  id: number
  x: number
  y: number
  category: Category
}

/** Pins for the potential detections: a coloured head on a stick over a ring on the ground. */
export class Markers {
  readonly group = new THREE.Group()
  private readonly pins = new Map<number, { pin: THREE.Group; category: Category; born: number }>()
  private readonly materials = new Map<Category, THREE.MeshStandardMaterial>()
  private readonly ringMaterials = new Map<Category, THREE.MeshBasicMaterial>()
  private readonly head = new THREE.SphereGeometry(0.28, 20, 14)
  private readonly hit = new THREE.SphereGeometry(0.7, 8, 6) // a bigger target for clicks and taps
  private readonly stick = new THREE.CylinderGeometry(0.03, 0.03, 1.2, 8)
  private readonly ring = new THREE.RingGeometry(0.35, 0.5, 32)
  private readonly hitMaterial = new THREE.MeshBasicMaterial({ visible: false })
  private readonly stickMaterial = new THREE.MeshStandardMaterial({ color: 0xf2f2f2 })
  private selected: number | null = null

  private material(c: Category) {
    let m = this.materials.get(c)
    if (!m) {
      m = new THREE.MeshStandardMaterial({ color: CATEGORY_COLORS[c], emissive: CATEGORY_COLORS[c], emissiveIntensity: 0.25 })
      this.materials.set(c, m)
    }
    return m
  }

  private ringMaterial(c: Category) {
    let m = this.ringMaterials.get(c)
    if (!m) {
      m = new THREE.MeshBasicMaterial({ color: CATEGORY_COLORS[c], transparent: true, opacity: 0.85, side: THREE.DoubleSide })
      this.ringMaterials.set(c, m)
    }
    return m
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
      const pin = new THREE.Group()
      pin.position.set(s.x, 0, -s.y)
      const stick = new THREE.Mesh(this.stick, this.stickMaterial)
      stick.position.y = 0.6
      const head = new THREE.Mesh(this.head, this.material(s.category))
      head.position.y = 1.3
      const hit = new THREE.Mesh(this.hit, this.hitMaterial)
      hit.position.y = 1.0
      hit.userData.detectionId = s.id
      const ring = new THREE.Mesh(this.ring, this.ringMaterial(s.category))
      ring.rotation.x = -Math.PI / 2
      ring.position.y = 0.04
      pin.add(stick, head, hit, ring)
      this.group.add(pin)
      this.pins.set(s.id, { pin, category: s.category, born: animate && !existing ? now : -Infinity })
    }
    this.select(this.selected)
  }

  select(id: number | null) {
    this.selected = id
    for (const [pid, p] of this.pins) p.pin.userData.selected = pid === id
  }

  /**
   * Pop-in of new markers, and a slow bob of the selected one. Time in seconds. Seen from far away the pins grow,
   * so they stay visible over the whole area (true size up close).
   */
  animate(now: number, camera: THREE.Camera) {
    for (const p of this.pins.values()) {
      const far = Math.min(6, Math.max(1, camera.position.distanceTo(p.pin.position) / 18))
      const u = Math.min(1, (now - p.born) / POP_S)
      const pop = u >= 1 ? 1 : 1 - Math.pow(1 - u, 3) * Math.cos(u * 6)
      const s = p.pin.userData.selected ? 1.35 + 0.08 * Math.sin(now * 4) : 1
      p.pin.scale.setScalar(Math.max(0.01, pop * s * far))
    }
  }

  /** The detection under a ray, if any. */
  pick(raycaster: THREE.Raycaster): number | null {
    const hits = raycaster.intersectObjects(this.group.children, true)
    for (const h of hits) if (h.object.userData.detectionId !== undefined) return h.object.userData.detectionId
    return null
  }

  dispose() {
    for (const g of [this.head, this.hit, this.stick, this.ring]) g.dispose()
    for (const m of [...this.materials.values(), ...this.ringMaterials.values(), this.hitMaterial, this.stickMaterial]) m.dispose()
  }
}
