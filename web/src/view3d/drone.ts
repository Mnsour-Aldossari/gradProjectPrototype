import * as THREE from 'three'

/** A small quadcopter about 0.7 m across, built from simple shapes, with its sensor payload underneath. */
export interface DroneModel {
  group: THREE.Group
  /** Turns the rotors; dt in seconds. */
  spin(dt: number): void
}

export function buildDrone(): DroneModel {
  const group = new THREE.Group()
  const dark = new THREE.MeshStandardMaterial({ color: 0x2b2f36, roughness: 0.6, metalness: 0.3 })
  const accent = new THREE.MeshStandardMaterial({ color: 0x1f5fad, roughness: 0.5 })

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.08, 0.34), dark)
  group.add(body)
  const canopy = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.05, 0.2), accent)
  canopy.position.set(0, 0.06, 0.02)
  group.add(canopy)

  // Front marker, so the heading shows (the nose points along -Z, north at heading 0).
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.1, 12), new THREE.MeshStandardMaterial({ color: 0xe0a526 }))
  nose.rotation.x = -Math.PI / 2
  nose.position.set(0, 0, -0.22)
  group.add(nose)

  // Sensor payload: metal detector coil and radar antenna under the body.
  const payload = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.03, 24), accent)
  payload.position.y = -0.12
  group.add(payload)
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.08, 8), dark)
  mast.position.y = -0.07
  group.add(mast)

  const rotors: THREE.Mesh[] = []
  const bladeMat = new THREE.MeshStandardMaterial({ color: 0xdddddd, transparent: true, opacity: 0.55 })
  for (const [sx, sz] of [
    [1, 1],
    [1, -1],
    [-1, 1],
    [-1, -1],
  ]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.025, 0.36), dark)
    arm.position.set((sx * 0.25) / 2, 0, (sz * 0.25) / 2)
    arm.rotation.y = Math.atan2(sx, sz)
    group.add(arm)
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.05, 12), dark)
    motor.position.set(sx * 0.25, 0.03, sz * 0.25)
    group.add(motor)
    const rotor = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.006, 0.025), bladeMat)
    rotor.position.set(sx * 0.25, 0.06, sz * 0.25)
    rotor.userData.dir = sx * sz
    group.add(rotor)
    rotors.push(rotor)
  }
  group.traverse((o) => {
    if (o instanceof THREE.Mesh) o.castShadow = true
  })

  return {
    group,
    spin(dt) {
      for (const r of rotors) r.rotation.y += r.userData.dir * dt * 40
    },
  }
}
