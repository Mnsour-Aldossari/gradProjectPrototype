import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import type { LatLon } from '../types'
import { buildDrone, type DroneModel } from './drone'
import { centredOn, toXY, type Frame } from './geo'
import { buildGround } from './ground'
import { Markers, type MarkerSpec } from './markers'
import { SCENE } from './palette'
import type { Pose } from './replay'

export type CameraMode = 'follow' | 'orbit' | 'top'
/** What can be shown or hidden from the Layers list. Likely clutter is a choice of markers, made by the page. */
export type Layer = 'flown' | 'planned' | 'scanned' | 'footprint' | 'buffers' | 'imagery'

const MARGIN_M = 40

/** Scene position of a point in the area's metres (east, north) at a height. */
const at = (x: number, y: number, h = 0) => new THREE.Vector3(x, h, -y)

function canvasTexture(size: [number, number], draw: (g: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  ;[c.width, c.height] = size
  draw(c.getContext('2d')!)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

/** PX4's takeoff (H) or landing (L) point: a ring on the ground with its letter. */
function pad(x: number, y: number, letter: 'H' | 'L', color: string): THREE.Mesh {
  const texture = canvasTexture([128, 128], (g) => {
    g.strokeStyle = color
    g.lineWidth = 7
    g.beginPath()
    g.arc(64, 64, 56, 0, Math.PI * 2)
    g.stroke()
    g.fillStyle = color
    g.globalAlpha = 0.16
    g.fill()
    g.globalAlpha = 1
    g.font = 'bold 64px system-ui, sans-serif'
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    g.fillText(letter, 64, 68)
  })
  const mesh = new THREE.Mesh(
    new THREE.CircleGeometry(1.3, 40),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.position.set(x, 0.06, -y)
  return mesh
}

/** A growable ribbon buffer: the positions only ever get appended. */
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
 * The 3D view of one survey, after the "Mission view" design: a dim ground (satellite imagery as a layer), the area as
 * a low translucent wall, the planned lanes, the track flown as a glowing line at its real height, the ground scanned,
 * the UAV with its sensor footprint, and diamond pins for the potential detections. Imperative three.js, driven by
 * View3DPage; `onFrame` runs after every frame so the page can place its labels, compass and scale bar.
 */
export class World {
  readonly frame: Frame
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private readonly controls: OrbitControls
  private readonly drone: DroneModel
  private readonly blob: THREE.Mesh
  private readonly footprint = new THREE.Group()
  private readonly cone: THREE.Mesh
  private readonly markers = new Markers()
  private trackGeometry = new LineGeometry()
  private readonly trackMaterials: LineMaterial[]
  private readonly trackLines = new THREE.Group()
  private trackArray = new Float32Array(3 * 4096)
  private readonly swath: Growable
  private readonly swathMesh: THREE.Mesh
  private readonly lanes: THREE.Line
  private readonly imagery: THREE.Mesh
  private readonly centre: THREE.Vector3
  readonly size: number
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
  private readonly v = new THREE.Vector3()
  onPick: (id: number | null) => void = () => {}
  onFrame: () => void = () => {}

  constructor(
    private readonly container: HTMLElement,
    area: LatLon[],
    path: LatLon[],
    private readonly swathWidthM: number,
    takeoff: LatLon | null = null,
    landing: LatLon | null = null,
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
    const reach = MARGIN_M + this.size * 3

    this.scene.background = new THREE.Color(SCENE.sky)
    this.scene.fog = new THREE.Fog(SCENE.sky, this.size * 1.6 + 60, reach * 1.4)
    this.camera = new THREE.PerspectiveCamera(48, 1, 0.1, 4000)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05 // stay above the ground
    this.controls.minDistance = 2
    this.controls.maxDistance = this.size * 4 + 60
    // The scene can be moved from the keyboard too: the arrow keys pan the view while the canvas has focus.
    const canvas = this.renderer.domElement
    canvas.tabIndex = 0
    canvas.setAttribute('role', 'img')
    canvas.setAttribute('aria-label', '3D view of the survey. With this focused, the arrow keys move the view.')
    this.controls.listenToKeyEvents(canvas)

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x4b4336, 1.3))
    const sun = new THREE.DirectionalLight(0xffffff, 1.2)
    sun.position.set(30, 60, 20)
    this.scene.add(sun)

    // Dim ground: earth tones darkening away from the area, with a faint grid for depth.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(reach * 2, reach * 2),
      new THREE.MeshBasicMaterial({
        map: canvasTexture([512, 512], (g) => {
          const grad = g.createRadialGradient(256, 256, 20, 256, 256, 256)
          grad.addColorStop(0, SCENE.groundNear)
          grad.addColorStop(1, SCENE.groundFar)
          g.fillStyle = grad
          g.fillRect(0, 0, 512, 512)
        }),
      }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.set(this.centre.x, -0.02, this.centre.z)
    this.scene.add(ground)
    const grid = new THREE.GridHelper(reach * 2, Math.round((reach * 2) / 10), SCENE.ink, SCENE.ink)
    ;(grid.material as THREE.Material).transparent = true
    ;(grid.material as THREE.Material).opacity = 0.05
    ;(grid.material as THREE.Material).depthWrite = false
    grid.position.set(this.centre.x, 0, this.centre.z)
    this.scene.add(grid)

    // Satellite imagery: a layer, off by default, dimmed so the overlays still read.
    this.imagery = buildGround(this.frame, area, MARGIN_M + this.size * 0.3)
    ;(this.imagery.material as THREE.MeshLambertMaterial).color.set(0x8c8c8c)
    this.imagery.position.y = 0.005
    this.imagery.visible = false
    this.scene.add(this.imagery)

    // Survey area: faint fill, a low translucent wall, its base and top edges and corner dots.
    const shape = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)))
    const fill = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshBasicMaterial({ color: SCENE.ink, transparent: true, opacity: 0.04, depthWrite: false }),
    )
    fill.rotation.x = -Math.PI / 2
    fill.position.y = 0.01
    this.scene.add(fill)
    const wallH = Math.max(1.2, this.size * 0.035)
    const ring = [...pts, pts[0]]
    const wallPos: number[] = []
    const wallUv: number[] = []
    for (let i = 0; i < pts.length; i++) {
      const [ax, ay] = ring[i]
      const [bx, by] = ring[i + 1]
      wallPos.push(ax, 0, -ay, bx, 0, -by, bx, wallH, -by, ax, 0, -ay, bx, wallH, -by, ax, wallH, -ay)
      wallUv.push(0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1)
    }
    const wallGeo = new THREE.BufferGeometry()
    wallGeo.setAttribute('position', new THREE.Float32BufferAttribute(wallPos, 3))
    wallGeo.setAttribute('uv', new THREE.Float32BufferAttribute(wallUv, 2))
    const fade = canvasTexture([4, 64], (g) => {
      const grad = g.createLinearGradient(0, 64, 0, 0)
      grad.addColorStop(0, 'rgba(230,234,242,0.3)')
      grad.addColorStop(1, 'rgba(230,234,242,0)')
      g.fillStyle = grad
      g.fillRect(0, 0, 4, 64)
    })
    this.scene.add(
      new THREE.Mesh(wallGeo, new THREE.MeshBasicMaterial({ map: fade, transparent: true, side: THREE.DoubleSide, depthWrite: false })),
    )
    const edge = (h: number, opacity: number) =>
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(ring.map(([x, y]) => at(x, y, h))),
        new THREE.LineBasicMaterial({ color: SCENE.ink, transparent: true, opacity }),
      )
    this.scene.add(edge(0.06, 0.75), edge(wallH, 0.22))
    const dot = new THREE.SphereGeometry(0.22, 12, 8)
    const dotMat = new THREE.MeshBasicMaterial({ color: SCENE.ink })
    for (const [x, y] of pts) {
      const d = new THREE.Mesh(dot, dotMat)
      d.position.copy(at(x, y, 0.06))
      this.scene.add(d)
    }

    // Planned lanes: faint dashes on the ground.
    const laneGeo = new THREE.BufferGeometry().setFromPoints(
      path.map(([lat, lon]) => {
        const [x, y] = toXY(this.frame, lat, lon)
        return at(x, y, 0.04)
      }),
    )
    this.lanes = new THREE.Line(
      laneGeo,
      new THREE.LineDashedMaterial({ color: SCENE.ink, transparent: true, opacity: 0.3, dashSize: 0.8, gapSize: 1 }),
    )
    this.lanes.computeLineDistances()
    this.scene.add(this.lanes)

    // Ground scanned: a translucent ribbon as wide as the lane spacing (two triangles per step of the track).
    const swathGeo = new THREE.BufferGeometry()
    this.swath = new Growable(swathGeo, 18, 4096)
    this.swathMesh = new THREE.Mesh(
      swathGeo,
      new THREE.MeshBasicMaterial({ color: SCENE.survey, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }),
    )
    this.swathMesh.frustumCulled = false
    this.scene.add(this.swathMesh)

    // Track flown, at the height it was flown: a soft glow under a bright core line.
    this.trackMaterials = [
      new LineMaterial({ color: SCENE.survey, linewidth: 7, transparent: true, opacity: 0.32, depthWrite: false }),
      new LineMaterial({ color: SCENE.surveyLight, linewidth: 1.8 }),
    ]
    for (const m of this.trackMaterials) {
      const line = new Line2(this.trackGeometry, m)
      line.frustumCulled = false
      this.trackLines.add(line)
    }
    this.trackLines.visible = false
    this.scene.add(this.trackLines)

    this.scene.add(this.markers.group)
    if (takeoff) this.scene.add(pad(...toXY(this.frame, takeoff[0], takeoff[1]), 'H', SCENE.ok))
    if (landing) this.scene.add(pad(...toXY(this.frame, landing[0], landing[1]), 'L', SCENE.landing))

    this.drone = buildDrone()
    this.drone.group.visible = false
    this.scene.add(this.drone.group)
    // A soft shadow under the UAV, so its height above the ground reads.
    this.blob = new THREE.Mesh(
      new THREE.CircleGeometry(0.4, 24),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.45, depthWrite: false }),
    )
    this.blob.rotation.x = -Math.PI / 2
    this.blob.visible = false
    this.scene.add(this.blob)

    // Sensor footprint: the patch of ground under the payload, a cone of view and the heading on the ground.
    const half = Math.max(0.5, swathWidthM / 2)
    const patch = new THREE.Mesh(
      new THREE.CircleGeometry(half, 40),
      new THREE.MeshBasicMaterial({ color: SCENE.survey, transparent: true, opacity: 0.3, depthWrite: false }),
    )
    const patchRim = new THREE.Mesh(
      new THREE.RingGeometry(half * 0.94, half, 48),
      new THREE.MeshBasicMaterial({ color: SCENE.surveyLight, side: THREE.DoubleSide }),
    )
    for (const m of [patch, patchRim]) {
      m.rotation.x = -Math.PI / 2
      m.position.y = 0.035
    }
    const chevron = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-0.35, 0.04, -half - 0.6),
        new THREE.Vector3(0, 0.04, -half - 1.1),
        new THREE.Vector3(0.35, 0.04, -half - 0.6),
      ]),
      new THREE.LineBasicMaterial({ color: SCENE.surveyLight }),
    )
    chevron.userData.heading = true
    this.cone = new THREE.Mesh(
      new THREE.ConeGeometry(half, 1, 32, 1, true),
      new THREE.MeshBasicMaterial({ color: SCENE.survey, transparent: true, opacity: 0.14, side: THREE.DoubleSide, depthWrite: false }),
    )
    this.footprint.add(patch, patchRim, chevron, this.cone)
    this.footprint.visible = false
    this.scene.add(this.footprint)

    this.setCamera('orbit')

    const el = this.renderer.domElement
    el.addEventListener('pointerdown', this.pointerDown)
    el.addEventListener('pointerup', this.pointerUp)
    this.observer = new ResizeObserver(() => this.resize())
    this.observer.observe(container)
    this.resize()
    this.loop()
  }

  setLayer(layer: Layer, on: boolean) {
    if (layer === 'flown') this.trackLines.visible = on && this.trackWritten > 1
    if (layer === 'planned') this.lanes.visible = on
    if (layer === 'scanned') this.swathMesh.visible = on
    if (layer === 'footprint') this.footprint.userData.on = on
    if (layer === 'buffers') this.markers.setBuffers(on)
    if (layer === 'imagery') this.imagery.visible = on
    this.trackLines.userData[layer] = on
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
      this.fit()
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

  /** The whole area in view, from the south-east and above, as in the design. */
  fit() {
    this.controls.target.copy(this.centre)
    const d = this.size * 0.95 + 14
    if (this.mode === 'top') this.camera.position.set(this.centre.x, this.size * 1.25 + 10, this.centre.z + 0.01)
    else this.camera.position.set(this.centre.x + d * 0.35, d * 0.75, this.centre.z + d * 0.85)
    this.controls.update()
  }

  /** Closer (factor < 1) or further (> 1) along the line of sight. */
  zoom(factor: number) {
    const offset = this.camera.position.clone().sub(this.controls.target)
    const len = Math.min(this.controls.maxDistance, Math.max(this.controls.minDistance, offset.length() * factor))
    this.camera.position.copy(this.controls.target).add(offset.setLength(len))
    this.controls.update()
  }

  /** Looks at a point (a detection, or the UAV) without changing the angle or the distance. */
  focus(x: number, y: number, h = 0) {
    const target = at(x, y, h)
    this.camera.position.add(target.clone().sub(this.controls.target))
    this.controls.target.copy(target)
    this.controls.update()
  }

  recenter() {
    if (this.shown) this.focus(this.shown.x, this.shown.y, this.shown.alt)
  }

  /** Screen position (px, within the view) of a point in the area's metres; null when behind or off screen. */
  project(x: number, y: number, h: number): { x: number; y: number } | null {
    this.v.copy(at(x, y, h)).project(this.camera)
    if (this.v.z > 1 || Math.abs(this.v.x) > 1.1 || Math.abs(this.v.y) > 1.1) return null
    return { x: ((this.v.x + 1) / 2) * this.container.clientWidth, y: ((1 - this.v.y) / 2) * this.container.clientHeight }
  }

  /** The way the camera faces, in compass degrees (0 = looking north). */
  azimuth(): number {
    const f = this.controls.target.clone().sub(this.camera.position)
    return ((Math.atan2(f.x, -f.z) * 180) / Math.PI + 360) % 360
  }

  /** Metres per screen pixel at the point looked at, for the scale bar. */
  metresPerPixel(): number {
    const d = this.camera.position.distanceTo(this.controls.target)
    return (2 * d * Math.tan((this.camera.fov * Math.PI) / 360)) / Math.max(1, this.container.clientHeight)
  }

  /** The UAV's pose as drawn (gliding between frames). */
  dronePose(): Pose | null {
    return this.shown
  }

  /** Forget what was drawn of the track: the next setTrack draws it again from its first pose. For a track that
   * changed under the scene, e.g. the stored part arriving after the first live frames. */
  resetTrack() {
    this.trackWritten = 0
    this.swathWritten = 0
  }

  /** Draws the first `count` poses of the track (poses only ever grow; a smaller count hides the rest, for replay). */
  setTrack(poses: Pose[], count: number) {
    if (count < this.swathWritten + 1) this.swathWritten = Math.max(0, count - 1)
    // Line positions: write what is new, then hand the whole buffer to the line geometry. Its size must stay the
    // same (three.js keeps the number of segments a line geometry first had), so a bigger track gets a new geometry.
    if (poses.length * 3 > this.trackArray.length) {
      const next = new Float32Array(Math.max(poses.length * 3, this.trackArray.length * 2))
      next.set(this.trackArray)
      this.trackArray = next
      this.trackGeometry.dispose()
      this.trackGeometry = new LineGeometry()
      for (const line of this.trackLines.children as Line2[]) line.geometry = this.trackGeometry
      this.trackWritten = 0 // rewritten below into the new geometry
    }
    // Everything known is written at once (a replay has the whole track), and only `count` of it is drawn.
    const upto = Math.max(poses.length, this.trackWritten)
    if (upto > this.trackWritten || this.trackWritten === 0) {
      for (let i = this.trackWritten; i < upto; i++) this.trackArray.set([poses[i].x, poses[i].alt, -poses[i].y], i * 3)
      this.trackWritten = upto
      if (this.trackWritten >= 2) this.trackGeometry.setPositions(this.trackArray)
    }
    this.trackGeometry.instanceCount = Math.max(0, count - 1)
    this.trackLines.visible = count > 1 && this.trackLines.userData.flown !== false

    this.swath.ensure(Math.max(0, count - 1))
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
    if (count - 1 > this.swathWritten) (this.swath.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    this.swathWritten = Math.max(this.swathWritten, count - 1)
    this.swath.geometry.setDrawRange(0, Math.max(0, count - 1) * 6)
  }

  /** Moves the UAV to a pose, gliding there over `glideMs` (0 jumps). null hides it. */
  setDrone(pose: Pose | null, glideMs: number) {
    if (!pose) {
      this.to = this.from = this.shown = null
      this.drone.group.visible = this.blob.visible = this.footprint.visible = false
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
    this.blob.scale.setScalar(Math.max(0.5, 1.2 - p.alt * 0.15))
    this.footprint.visible = this.footprint.userData.on !== false && p.alt > 0.2
    this.footprint.position.set(p.x, 0, -p.y)
    this.footprint.rotation.y = -(p.heading * Math.PI) / 180
    this.cone.scale.y = Math.max(0.01, p.alt)
    this.cone.position.y = p.alt / 2
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
    for (const m of this.trackMaterials) m.resolution.set(w, h)
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
    this.markers.animate(now / 1000, this.camera, this.reducedMotion)
    if (this.shown) {
      // Like the pins, the UAV grows when seen from far away (true size up close), around its own centre.
      const far = Math.min(4, Math.max(1, this.camera.position.distanceTo(this.drone.group.position) / 25))
      this.drone.group.scale.setScalar(far)
    }
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
    this.onFrame()
  }

  dispose() {
    cancelAnimationFrame(this.frameId)
    this.observer.disconnect()
    this.renderer.domElement.removeEventListener('pointerdown', this.pointerDown)
    this.renderer.domElement.removeEventListener('pointerup', this.pointerUp)
    this.controls.dispose()
    this.markers.dispose()
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.Line || o instanceof THREE.Sprite) {
        o.geometry.dispose()
        const mats = Array.isArray(o.material) ? o.material : [o.material]
        for (const m of mats) {
          ;(m as THREE.MeshBasicMaterial).map?.dispose()
          m.dispose()
        }
      }
    })
    this.trackGeometry.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }
}
