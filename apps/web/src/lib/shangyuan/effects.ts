import * as THREE from 'three'

export interface Effect {
  update(dt: number): boolean
  dispose(scene: THREE.Scene): void
}

/** Additive point burst with gravity and drag. Used for sparks, embers and fireworks. */
export class ParticleBurst implements Effect {
  protected readonly points: THREE.Points
  protected readonly flash: THREE.Sprite | null = null
  protected readonly positions: Float32Array
  protected readonly velocities: Float32Array
  protected age = 0
  protected life = 3
  protected gravity = 3.2
  protected drag = 0.985
  protected readonly scene: THREE.Scene

  constructor(
    scene: THREE.Scene,
    glow: THREE.Texture,
    origin: THREE.Vector3,
    options: {
      count: number
      color: THREE.ColorRepresentation
      spread: number
      speed: number
      size?: number
      life?: number
      gravity?: number
      drag?: number
      /** Emit on a sphere with a tight speed band: a firework shell, not a fountain. */
      shell?: boolean
    },
  ) {
    this.scene = scene
    this.life = options.life ?? 3
    this.gravity = options.gravity ?? 3.2
    this.drag = options.drag ?? 0.985
    const count = options.count
    this.positions = new Float32Array(count * 3)
    this.velocities = new Float32Array(count * 3)
    const colors = new Float32Array(count * 3)
    const c = new THREE.Color(options.color)

    for (let i = 0; i < count; i++) {
      const dir = new THREE.Vector3()
      if (options.shell) {
        const y = Math.random() * 2 - 1
        const a = Math.random() * Math.PI * 2
        const r = Math.sqrt(1 - y * y)
        dir.set(r * Math.cos(a), y, r * Math.sin(a))
      } else {
        dir
          .set(Math.random() - 0.5, Math.random() * options.spread, Math.random() - 0.5)
          .normalize()
      }
      const v =
        options.speed * (options.shell ? 0.9 + Math.random() * 0.12 : 0.4 + Math.random() * 0.8)
      // Start each spark a fraction of a second into its flight.  Without this
      // every particle sits on the origin on the first frame and hundreds of
      // additive sprites stack into a full-screen white flash.
      const preAge = Math.random() * 0.32
      this.positions[i * 3] = origin.x + dir.x * v * preAge
      this.positions[i * 3 + 1] = origin.y + dir.y * v * preAge
      this.positions[i * 3 + 2] = origin.z + dir.z * v * preAge
      this.velocities[i * 3] = dir.x * v
      this.velocities[i * 3 + 1] = dir.y * v
      this.velocities[i * 3 + 2] = dir.z * v
      const t = 0.72 + Math.random() * 0.4
      colors[i * 3] = c.r * t
      colors[i * 3 + 1] = c.g * t
      colors[i * 3 + 2] = c.b * t
    }

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(this.positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    this.points = new THREE.Points(
      geo,
      new THREE.PointsMaterial({
        size: options.size ?? 0.5,
        vertexColors: true,
        transparent: true,
        opacity: 1,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        map: glow,
        sizeAttenuation: true,
      }),
    )
    this.points.frustumCulled = false
    scene.add(this.points)
    if (options.shell) {
      this.flash = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glow,
          color: options.color,
          transparent: true,
          opacity: 0.85,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      )
      this.flash.position.copy(origin)
      this.flash.scale.setScalar(3)
      scene.add(this.flash)
    }
  }

  update(dt: number) {
    this.age += dt
    if (this.flash) {
      const k = Math.min(1, this.age / 0.4)
      this.flash.scale.setScalar(3 + k * 11)
      this.flash.material.opacity = 0.85 * (1 - k)
      this.flash.visible = k < 1
    }
    const count = this.positions.length / 3
    for (let i = 0; i < count; i++) {
      this.velocities[i * 3 + 1] -= this.gravity * dt
      for (let k = 0; k < 3; k++) {
        this.velocities[i * 3 + k] *= this.drag
        this.positions[i * 3 + k] += this.velocities[i * 3 + k] * dt
      }
    }
    ;(this.points.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true
    const mat = this.points.material as THREE.PointsMaterial
    // A short fade-in keeps the shell from flashing the whole frame at birth.
    mat.opacity = Math.min(1, this.age / 0.18) * Math.max(0, 1 - this.age / this.life)
    return this.age < this.life
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.points)
    this.points.geometry.dispose()
    ;(this.points.material as THREE.Material).dispose()
    if (this.flash) {
      scene.remove(this.flash)
      this.flash.material.dispose()
    }
  }
}

/** A high shell that breaks into falling gold sparks: the iron-flower beat. */
export class IronFlower implements Effect {
  private readonly bursts: ParticleBurst[]
  private readonly light: THREE.PointLight
  private readonly halo: THREE.Sprite
  private readonly core: THREE.Sprite
  private age = 0

  constructor(scene: THREE.Scene, glow: THREE.Texture, origin: THREE.Vector3) {
    this.bursts = [
      new ParticleBurst(scene, glow, origin, {
        count: 900,
        color: 0xffe3b4,
        spread: 1.5,
        speed: 20,
        size: 0.26,
        life: 3.6,
        gravity: 5.4,
        drag: 0.975,
      }),
      new ParticleBurst(scene, glow, origin, {
        count: 420,
        color: 0xff9a4c,
        spread: 1.2,
        speed: 14,
        size: 0.32,
        life: 3.2,
        gravity: 4.2,
        drag: 0.98,
      }),
    ]
    // A bright core so the burst reads as molten iron, not a distant firework.
    this.core = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color: 0xffe6b8,
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    this.core.position.copy(origin)
    this.core.scale.setScalar(2.4)
    scene.add(this.core)
    this.light = new THREE.PointLight(0xffb066, 55, 55, 2)
    this.light.position.copy(origin)
    scene.add(this.light)
    this.halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color: 0xffb877,
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    this.halo.position.copy(origin)
    this.halo.scale.setScalar(3)
    scene.add(this.halo)
  }

  update(dt: number) {
    this.age += dt
    this.light.intensity = Math.max(0, 55 * (1 - this.age / 3.6))
    this.core.scale.setScalar(2.4 + this.age * 2.2)
    this.core.material.opacity = Math.max(0, 0.95 - this.age / 0.5)
    const s = 3 + this.age * 0.9
    this.halo.scale.setScalar(s)
    this.halo.material.opacity = Math.max(0, 0.22 * (1 - this.age / 2))
    let alive = this.age < 3.6
    for (const b of this.bursts) alive = b.update(dt) || alive
    return alive
  }

  dispose(scene: THREE.Scene) {
    this.bursts.forEach((b) => {
      b.dispose(scene)
    })
    scene.remove(this.light)
    scene.remove(this.halo)
    scene.remove(this.core)
    this.halo.material.dispose()
    this.core.material.dispose()
  }
}

/** A slow expanding ring on the water where a lantern is set down. */
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
  private readonly bats: THREE.Sprite[] = []
  private readonly batData: {
    cx: number
    cy: number
    cz: number
    r: number
    phase: number
    speed: number
    flap: number
  }[] = []
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

    // A small dusk flock above the canal. Sprites keep the silhouette soft and
    // cost one draw call each; the flock stays high enough to clear the eaves.
    if (bat) {
      const batCount = 12
      for (let i = 0; i < batCount; i++) {
        const material = new THREE.SpriteMaterial({
          map: bat,
          color: 0xffffff,
          transparent: true,
          opacity: 0.88,
          depthWrite: false,
        })
        const sprite = new THREE.Sprite(material)
        const scale = 0.9 + rng() * 0.7
        sprite.scale.set(scale * 1.8, scale, 1)
        const cx = -18 + rng() * 36
        const cy = 8.5 + rng() * 8.0
        const cz = -110 + rng() * 260
        const r = 2.5 + rng() * 5.0
        const phase = rng() * Math.PI * 2
        const speed = 0.12 + rng() * 0.18
        const flap = rng() * Math.PI * 2
        this.bats.push(sprite)
        this.batData.push({ cx, cy, cz, r, phase, speed, flap })
        this.object.add(sprite)
      }
    }
  }

  update(dt: number) {
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
    for (let i = 0; i < this.bats.length; i++) {
      const d = this.batData[i]
      const sprite = this.bats[i]
      const a = this.time * d.speed + d.phase
      sprite.position.set(
        d.cx + Math.cos(a) * d.r,
        d.cy + Math.sin(this.time * 0.7 + d.flap) * 0.8,
        d.cz + Math.sin(a) * d.r * 0.7,
      )
      const flap = 0.35 + Math.abs(Math.sin(this.time * 7.0 + d.flap)) * 0.65
      sprite.scale.y = sprite.scale.x * 0.55 * flap
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
    const batMap = this.bats[0]?.material.map
    for (const bat of this.bats) {
      bat.material.dispose()
    }
    batMap?.dispose()
  }
}
