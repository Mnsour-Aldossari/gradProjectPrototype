import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { COLORS } from '../theme'
import type { LatLon } from '../types'
import { buildDrone, type DroneModel } from './drone'
import { centredOn, toXY, type Frame } from './geo'
import { buildGround } from './ground'
import { Markers, type MarkerSpec } from './markers'
import type { Pose } from './replay'

export type CameraMode = 'follow' | 'orbit' | 'top'

const MARGIN_M = 40
const TRACK_COLOR = 0x38bdf8

/** Scene position of a point in the area's metres (east, north) at a height. */
const at = (x: number, y: number, h = 0) => new THREE.Vector3(x, h, -y)

/** A growable line or ribbon buffer: the positions only ever get appended. */
class Growable {
  array: Float32Array
  constructor(
    readonly geometry: THREE.BufferGeometry,
    private readonly perItem: number,
    capacity: number,
  ) {
    this.array = new Float32Array(capacity * perItem)
    geometry.setAttribute('position', new THREE.BufferAttribute(this.array, 3))
  }
  ensure(items: number) {
    if (items * this.perItem <= this.array.length) return
    const next = new Float32Array(Math.max(items * this.perItem, this.array.length * 2))
    next.set(this.array)
    this.array = next
    this.geometry.setAttribute('position', new THREE.BufferAttribute(this.array, 3))
  }
}

/**
 * The 3D view of one survey: satellite ground, the area and the planned lanes, the UAV, the track it flew in the air,
 * the ground it scanned, and pins for the potential detections. Imperative three.js, driven by View3DPage.
 */
export class World {
  readonly frame: Frame
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private readonly controls: OrbitControls
  private readonly drone: DroneModel
  private readonly blob: THREE.Mesh
  private readonly markers = new Markers()
  private readonly track: Growable
  private readonly trackLine: THREE.Line
  private readonly swath: Growable
  private readonly swathMesh: THREE.Mesh
  private readonly centre: THREE.Vector3
  private readonly size: number
  private readonly hemi: THREE.HemisphereLight
  private trackWritten = 0
  private swathWritten = 0
  private mode: CameraMode = 'orbit'
  private from: Pose | null = null
  private to: Pose | null = null
  private moveStart = 0
  private moveMs = 1
  private shown: Pose | null = null
  private frameId = 0
  private last = performance.now()
  private readonly observer: ResizeObserver
  private readonly reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  private down: { x: number; y: number } | null = null
  onPick: (id: number | null) => void = () => {}

  constructor(
    private readonly container: HTMLElement,
    area: LatLon[],
    path: LatLon[],
    private readonly swathWidthM: number,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true }) // throws without WebGL; the page shows a message
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    container.appendChild(this.renderer.domElement)
    this.renderer.domElement.setAttribute('aria-hidden', 'true')

    this.frame = centredOn(area)
    const pts = area.map((p) => toXY(this.frame, p[0], p[1]))
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    this.centre = at((Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2)
    this.size = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05 // stay above the ground
    this.controls.minDistance = 2
    this.controls.maxDistance = this.size * 4 + 50

    this.hemi = new THREE.HemisphereLight(0xffffff, 0x8a7a5a, 1.6)
    this.scene.add(this.hemi)
    const sun = new THREE.DirectionalLight(0xffffff, 1.4)
    sun.position.set(30, 60, 20)
    this.scene.add(sun)

    this.scene.add(buildGround(this.frame, area, MARGIN_M + this.size * 0.3))

    // Survey area: a dashed red outline, as on the map.
    const outline = new THREE.BufferGeometry().setFromPoints([...pts, pts[0]].map(([x, y]) => at(x, y, 0.05)))
    const outlineLine = new THREE.Line(outline, new THREE.LineDashedMaterial({ color: COLORS.hazard, dashSize: 1.2, gapSize: 0.8 }))
    outlineLine.computeLineDistances()
    this.scene.add(outlineLine)

    // Planned lanes, faint on the ground.
    const lanes = new THREE.BufferGeometry().setFromPoints(
      path.map(([lat, lon]) => {
        const [x, y] = toXY(this.frame, lat, lon)
        return at(x, y, 0.04)
      }),
    )
    this.scene.add(new THREE.Line(lanes, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 })))

    // Ground scanned: a translucent ribbon as wide as the lane spacing (two triangles per step of the track).
    const swathGeo = new THREE.BufferGeometry()
    this.swath = new Growable(swathGeo, 18, 4096)
    this.swathMesh = new THREE.Mesh(
      swathGeo,
      new THREE.MeshBasicMaterial({ color: COLORS.survey, transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false }),
    )
    this.scene.add(this.swathMesh)

    // Track flown, in the air at the height it was flown.
    const trackGeo = new THREE.BufferGeometry()
    this.track = new Growable(trackGeo, 3, 4096)
    this.trackLine = new THREE.Line(trackGeo, new THREE.LineBasicMaterial({ color: TRACK_COLOR }))
    this.trackLine.frustumCulled = false
    this.swathMesh.frustumCulled = false
    this.scene.add(this.trackLine)

    this.scene.add(this.markers.group)

    this.drone = buildDrone()
    this.drone.group.visible = false
    this.scene.add(this.drone.group)
    // A soft shadow under the UAV, so its height above the ground reads.
    this.blob = new THREE.Mesh(
      new THREE.CircleGeometry(0.4, 24),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35, depthWrite: false }),
    )
    this.blob.rotation.x = -Math.PI / 2
    this.blob.visible = false
    this.scene.add(this.blob)

    this.setCamera('top')
    this.setCamera('orbit')

    const el = this.renderer.domElement
    el.addEventListener('pointerdown', this.pointerDown)
    el.addEventListener('pointerup', this.pointerUp)
    this.observer = new ResizeObserver(() => this.resize())
    this.observer.observe(container)
    this.resize()
    this.loop()
  }

  setDark(dark: boolean) {
    const sky = new THREE.Color(dark ? 0x0b1220 : 0xbfd8ec)
    this.scene.background = sky
    this.scene.fog = new THREE.Fog(sky, this.size * 2 + 60, this.size * 6 + 200)
    this.hemi.intensity = dark ? 1.1 : 1.6
  }

  setCamera(mode: CameraMode) {
    this.mode = mode
    const target = this.shown ? at(this.shown.x, this.shown.y, this.shown.alt) : this.centre
    if (mode === 'top') {
      this.controls.enableRotate = false
      this.controls.target.copy(this.centre)
      this.camera.position.set(this.centre.x, this.size * 1.25 + 10, this.centre.z + 0.01)
    } else if (mode === 'orbit') {
      this.controls.enableRotate = true
      this.controls.target.copy(target)
      const d = this.size * 0.9 + 12
      this.camera.position.set(target.x + d * 0.5, d * 0.6, target.z + d * 0.75)
    } else {
      // Follow: close behind the UAV from the side the camera looks from; it can still be turned and zoomed.
      this.controls.enableRotate = true
      const dir = this.camera.position.clone().sub(this.controls.target).setY(0)
      if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1)
      dir.normalize().multiplyScalar(9)
      this.controls.target.copy(target)
      this.camera.position.copy(target).add(dir).setY(target.y + 5)
    }
    this.controls.update()
  }

  /** Draws the first `count` poses of the track (poses only ever grow; a smaller count hides the rest, for replay). */
  setTrack(poses: Pose[], count: number) {
    if (count < this.trackWritten) {
      this.trackWritten = Math.min(this.trackWritten, count)
      this.swathWritten = Math.min(this.swathWritten, Math.max(0, count - 1))
    }
    this.track.ensure(count)
    this.swath.ensure(Math.max(0, count - 1))
    for (let i = this.trackWritten; i < count; i++) {
      const p = poses[i]
      this.track.array.set([p.x, p.alt, -p.y], i * 3)
    }
    const half = this.swathWidthM / 2
    for (let i = Math.max(1, this.swathWritten + 1); i < count; i++) {
      const a = poses[i - 1]
      const b = poses[i]
      const len = Math.hypot(b.x - a.x, b.y - a.y)
      const [nx, ny] = len > 1e-6 ? [-(b.y - a.y) / len, (b.x - a.x) / len] : [0, 0]
      const q = (x: number, y: number) => [x, 0.03, -y]
      const al = q(a.x + nx * half, a.y + ny * half)
      const ar = q(a.x - nx * half, a.y - ny * half)
      const bl = q(b.x + nx * half, b.y + ny * half)
      const br = q(b.x - nx * half, b.y - ny * half)
      this.swath.array.set([...al, ...ar, ...bl, ...bl, ...ar, ...br], (i - 1) * 18)
    }
    if (count > this.trackWritten) (this.track.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    if (count - 1 > this.swathWritten) (this.swath.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    this.trackWritten = Math.max(this.trackWritten, count)
    this.swathWritten = Math.max(this.swathWritten, count - 1)
    this.track.geometry.setDrawRange(0, count)
    this.swath.geometry.setDrawRange(0, Math.max(0, count - 1) * 6)
  }

  /** Moves the UAV to a pose, gliding there over `glideMs` (0 jumps). null hides it. */
  setDrone(pose: Pose | null, glideMs: number) {
    if (!pose) {
      this.to = this.from = this.shown = null
      this.drone.group.visible = this.blob.visible = false
      return
    }
    this.from = glideMs > 0 && this.shown ? this.shown : pose
    this.to = pose
    this.moveStart = performance.now()
    this.moveMs = Math.max(1, glideMs)
    if (!this.shown) this.placeDrone(pose)
  }

  setMarkers(specs: MarkerSpec[], animate: boolean) {
    this.markers.set(specs, performance.now() / 1000, animate && !this.reducedMotion)
  }

  selectMarker(id: number | null) {
    this.markers.select(id)
  }

  private placeDrone(p: Pose) {
    this.shown = p
    this.drone.group.visible = this.blob.visible = true
    this.drone.group.position.set(p.x, p.alt + 0.12, -p.y) // the payload hangs 0.12 m under the body
    this.drone.group.rotation.y = -(p.heading * Math.PI) / 180
    this.blob.position.set(p.x, 0.02, -p.y)
    const s = Math.max(0.5, 1.2 - p.alt * 0.15)
    this.blob.scale.setScalar(s)
  }

  private pointerDown = (e: PointerEvent) => {
    this.down = { x: e.clientX, y: e.clientY }
  }

  private pointerUp = (e: PointerEvent) => {
    if (!this.down || Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y) > 6) return
    const rect = this.renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
    const ray = new THREE.Raycaster()
    ray.setFromCamera(ndc, this.camera)
    this.onPick(this.markers.pick(ray))
  }

  private resize() {
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  private loop = () => {
    this.frameId = requestAnimationFrame(this.loop)
    const now = performance.now()
    const dt = Math.min(0.1, (now - this.last) / 1000)
    this.last = now

    if (this.from && this.to) {
      const u = Math.min(1, (now - this.moveStart) / this.moveMs)
      const a = this.from
      const b = this.to
      const dh = ((((b.heading - a.heading) % 360) + 540) % 360) - 180
      this.placeDrone({
        ...b,
        x: a.x + (b.x - a.x) * u,
        y: a.y + (b.y - a.y) * u,
        alt: a.alt + (b.alt - a.alt) * u,
        heading: (a.heading + dh * u + 360) % 360,
      })
    }
    if (this.shown && !this.reducedMotion) this.drone.spin(dt)

    if (this.mode === 'follow' && this.shown) {
      // Carry the camera along with the UAV, keeping the angle and distance the user chose.
      const target = at(this.shown.x, this.shown.y, this.shown.alt)
      this.camera.position.add(target.clone().sub(this.controls.target))
      this.controls.target.copy(target)
    }
    this.markers.animate(now / 1000, this.camera)
    if (this.shown) {
      // Like the pins, the UAV grows when seen from far away (true size up close), around its own centre.
      const far = Math.min(4, Math.max(1, this.camera.position.distanceTo(this.drone.group.position) / 25))
      this.drone.group.scale.setScalar(far)
    }
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  dispose() {
    cancelAnimationFrame(this.frameId)
    this.observer.disconnect()
    this.renderer.domElement.removeEventListener('pointerdown', this.pointerDown)
    this.renderer.domElement.removeEventListener('pointerup', this.pointerUp)
    this.controls.dispose()
    this.markers.dispose()
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.Line) {
        o.geometry.dispose()
        const mats = Array.isArray(o.material) ? o.material : [o.material]
        for (const m of mats) {
          ;(m as THREE.MeshBasicMaterial).map?.dispose()
          m.dispose()
        }
      }
    })
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }
}
