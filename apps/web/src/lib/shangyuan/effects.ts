import * as THREE from 'three'

export interface Effect {
  update(dt: number): boolean
  dispose(scene: THREE.Scene): void
}

export class Ripple implements Effect {
  private readonly mesh: THREE.Mesh
  private age = 0

  constructor(scene: THREE.Scene, origin: THREE.Vector3) {
    const geo = new THREE.RingGeometry(0.18, 0.26, 48)
    const mat = new THREE.MeshBasicMaterial({
      color: 0xffc98a,
      transparent: true,
      opacity: 0.8,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    this.mesh = new THREE.Mesh(geo, mat)
    this.mesh.rotation.x = -Math.PI / 2
    this.mesh.position.copy(origin)
    this.mesh.position.y = 0.09
    scene.add(this.mesh)
  }

  update(dt: number) {
    this.age += dt
    const s = 1 + this.age * 3.4
    this.mesh.scale.setScalar(s)
    ;(this.mesh.material as THREE.MeshBasicMaterial).opacity = Math.max(
      0,
      0.8 * (1 - this.age / 2.2),
    )
    return this.age < 2.2
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.mesh)
    this.mesh.geometry.dispose()
    ;(this.mesh.material as THREE.Material).dispose()
  }
}

/**
 * Slow petals and low mist along the river. Two point clouds keep the reference's
 * layered depth without adding a draw call per speck.
 */
export class RiverAtmosphere {
  readonly object = new THREE.Group()
  private readonly petals: THREE.Points
  private readonly mist: THREE.Points
  private readonly petalPositions: Float32Array
  private readonly petalVelocities: Float32Array
  private readonly petalPhases: Float32Array
  private readonly mistPositions: Float32Array
  private readonly mistPhases: Float32Array
  private readonly fireflies: THREE.Points
  private readonly fireflyPositions: Float32Array
  private readonly fireflyPhases: Float32Array
  private bats: THREE.InstancedMesh | null = null
  private readonly batData: {
    cx: number
    cy: number
    cz: number
    r: number
    phase: number
    speed: number
    flap: number
    size: number
  }[] = []
  private readonly batMatrix = new THREE.Matrix4()
  private readonly batPosition = new THREE.Vector3()
  private readonly batScale = new THREE.Vector3()
  private time = 0

  constructor(glow: THREE.Texture, bat?: THREE.Texture) {
    let seed = 0x5f3759df
    const rng = () => {
      seed = (seed + 0x6d2b79f5) | 0
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }

    const petalCount = 520
    this.petalPositions = new Float32Array(petalCount * 3)
    this.petalVelocities = new Float32Array(petalCount * 3)
    this.petalPhases = new Float32Array(petalCount)
    const petalColors = new Float32Array(petalCount * 3)
    const palette = ['#ffc2d6', '#ffe0ea', '#f4a6c2'].map((c) => new THREE.Color(c))
    for (let i = 0; i < petalCount; i++) {
      this.petalPositions[i * 3] = -26 + rng() * 52
      this.petalPositions[i * 3 + 1] = 1.2 + rng() * 15
      this.petalPositions[i * 3 + 2] = -140 + rng() * 320
      this.petalVelocities[i * 3] = (rng() - 0.5) * 0.14
      this.petalVelocities[i * 3 + 1] = -0.1 - rng() * 0.14
      this.petalVelocities[i * 3 + 2] = 0.22 + rng() * 0.38
      this.petalPhases[i] = rng() * Math.PI * 2
      const c = palette[Math.floor(rng() * palette.length)]
      petalColors[i * 3] = c.r
      petalColors[i * 3 + 1] = c.g
      petalColors[i * 3 + 2] = c.b
    }
    const petalGeo = new THREE.BufferGeometry()
    petalGeo.setAttribute('position', new THREE.BufferAttribute(this.petalPositions, 3))
    petalGeo.setAttribute('color', new THREE.BufferAttribute(petalColors, 3))
    this.petals = new THREE.Points(
      petalGeo,
      new THREE.PointsMaterial({
        size: 0.52,
        map: glow,
        vertexColors: true,
        transparent: true,
        opacity: 0.7,
        depthWrite: false,
        sizeAttenuation: true,
      }),
    )
    this.petals.frustumCulled = false
    this.object.add(this.petals)

    const mistCount = 34
    this.mistPositions = new Float32Array(mistCount * 3)
    this.mistPhases = new Float32Array(mistCount)
    for (let i = 0; i < mistCount; i++) {
      this.mistPositions[i * 3] = -22 + rng() * 44
      this.mistPositions[i * 3 + 1] = 0.9 + rng() * 1.7
      this.mistPositions[i * 3 + 2] = -130 + rng() * 300
      this.mistPhases[i] = rng() * Math.PI * 2
    }
    const mistGeo = new THREE.BufferGeometry()
    mistGeo.setAttribute('position', new THREE.BufferAttribute(this.mistPositions, 3))
    this.mist = new THREE.Points(
      mistGeo,
      new THREE.PointsMaterial({
        size: 4.2,
        map: glow,
        color: new THREE.Color('#5a5aa8'),
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
        sizeAttenuation: true,
      }),
    )
    this.mist.frustumCulled = false
    this.object.add(this.mist)

    // Fireflies hug the quay edge, where the warm shop light meets the reeds.
    const fireflyCount = 420
    this.fireflyPositions = new Float32Array(fireflyCount * 3)
    this.fireflyPhases = new Float32Array(fireflyCount)
    const fireflyColors = new Float32Array(fireflyCount * 3)
    const fireflyPalette = ['#ffe6a0', '#d8ff9a', '#ffcf70'].map((c) => new THREE.Color(c))
    for (let i = 0; i < fireflyCount; i++) {
      const side = rng() < 0.5 ? -1 : 1
      this.fireflyPositions[i * 3] = side * (12.6 + rng() * 6.6)
      this.fireflyPositions[i * 3 + 1] = 0.7 + rng() * 4.6
      this.fireflyPositions[i * 3 + 2] = -140 + rng() * 320
      this.fireflyPhases[i] = rng() * Math.PI * 2
      const c = fireflyPalette[Math.floor(rng() * fireflyPalette.length)]
      fireflyColors[i * 3] = c.r
      fireflyColors[i * 3 + 1] = c.g
      fireflyColors[i * 3 + 2] = c.b
    }
    const fireflyGeo = new THREE.BufferGeometry()
    fireflyGeo.setAttribute('position', new THREE.BufferAttribute(this.fireflyPositions, 3))
    fireflyGeo.setAttribute('color', new THREE.BufferAttribute(fireflyColors, 3))
    this.fireflies = new THREE.Points(
      fireflyGeo,
      new THREE.PointsMaterial({
        size: 0.24,
        map: glow,
        vertexColors: true,
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
      }),
    )
    this.fireflies.frustumCulled = false
    this.object.add(this.fireflies)

    // A small dusk flock above the canal.  Twelve sprites used to cost twelve
    // draw calls; one InstancedMesh keeps the same camera-facing quads and
    // per-bird flap while the flock stays a single call.
    if (bat) {
      const batCount = 12
      const geometry = new THREE.PlaneGeometry(1, 1)
      const material = new THREE.MeshBasicMaterial({
        map: bat,
        color: 0xffffff,
        transparent: true,
        opacity: 0.88,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
      const mesh = new THREE.InstancedMesh(geometry, material, batCount)
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      mesh.frustumCulled = false
      mesh.userData.noGtao = true
      mesh.count = batCount
      for (let i = 0; i < batCount; i++) {
        const scale = 0.9 + rng() * 0.7
        const cx = -18 + rng() * 36
        const cy = 8.5 + rng() * 8.0
        const cz = -110 + rng() * 260
        const r = 2.5 + rng() * 5.0
        const phase = rng() * Math.PI * 2
        const speed = 0.12 + rng() * 0.18
        const flap = rng() * Math.PI * 2
        this.batData.push({ cx, cy, cz, r, phase, speed, flap, size: scale * 1.8 })
      }
      this.bats = mesh
      this.object.add(mesh)
    }
  }

  update(dt: number, camera?: THREE.Camera) {
    this.time += dt
    for (let i = 0; i < this.petalPhases.length; i++) {
      const p = i * 3
      this.petalPositions[p] +=
        (this.petalVelocities[p] + Math.sin(this.time + this.petalPhases[i]) * 0.12) * dt
      this.petalPositions[p + 1] += this.petalVelocities[p + 1] * dt
      this.petalPositions[p + 2] += this.petalVelocities[p + 2] * dt
      if (this.petalPositions[p + 2] > 182) this.petalPositions[p + 2] = -140
      if (this.petalPositions[p + 1] < 0.7) this.petalPositions[p + 1] = 16
    }
    for (let i = 0; i < this.mistPhases.length; i++) {
      const p = i * 3
      this.mistPositions[p + 2] += 0.09 * dt
      this.mistPositions[p + 1] += Math.sin(this.time * 0.35 + this.mistPhases[i]) * 0.0015
      if (this.mistPositions[p + 2] > 180) this.mistPositions[p + 2] = -140
    }
    for (let i = 0; i < this.fireflyPhases.length; i++) {
      const p = i * 3
      this.fireflyPositions[p] += Math.cos(this.time * 1.3 + this.fireflyPhases[i]) * 0.0015
      this.fireflyPositions[p + 1] += Math.sin(this.time * 1.7 + this.fireflyPhases[i]) * 0.0025
      this.fireflyPositions[p + 2] += 0.02 * dt
      if (this.fireflyPositions[p + 2] > 182) this.fireflyPositions[p + 2] = -140
    }
    if (this.bats && camera) {
      for (let i = 0; i < this.batData.length; i++) {
        const d = this.batData[i]
        const a = this.time * d.speed + d.phase
        this.batPosition.set(
          d.cx + Math.cos(a) * d.r,
          d.cy + Math.sin(this.time * 0.7 + d.flap) * 0.8,
          d.cz + Math.sin(a) * d.r * 0.7,
        )
        const flap = 0.35 + Math.abs(Math.sin(this.time * 7.0 + d.flap)) * 0.65
        this.batScale.set(d.size, d.size * 0.55 * flap, 1)
        this.batMatrix.compose(this.batPosition, camera.quaternion, this.batScale)
        this.bats.setMatrixAt(i, this.batMatrix)
      }
      this.bats.instanceMatrix.needsUpdate = true
    }
    ;(this.petals.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    ;(this.mist.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    ;(this.fireflies.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.object)
    this.petals.geometry.dispose()
    ;(this.petals.material as THREE.Material).dispose()
    this.mist.geometry.dispose()
    ;(this.mist.material as THREE.Material).dispose()
    this.fireflies.geometry.dispose()
    ;(this.fireflies.material as THREE.Material).dispose()
    if (this.bats) {
      const material = this.bats.material as THREE.MeshBasicMaterial
      material.map?.dispose()
      material.dispose()
      this.bats.geometry.dispose()
    }
  }
}
