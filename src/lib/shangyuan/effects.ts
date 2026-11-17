import * as THREE from 'three'

export interface Effect {
  update(dt: number): boolean
  dispose(scene: THREE.Scene): void
}

/** Additive point burst with gravity and drag. Used for sparks, embers and fireworks. */
export class ParticleBurst implements Effect {
  protected readonly points: THREE.Points
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
      this.positions[i * 3] = origin.x
      this.positions[i * 3 + 1] = origin.y
      this.positions[i * 3 + 2] = origin.z
      const dir = new THREE.Vector3(Math.random() - 0.5, Math.random() * options.spread, Math.random() - 0.5).normalize()
      const v = options.speed * (0.4 + Math.random() * 0.8)
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
  }

  update(dt: number) {
    this.age += dt
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
    mat.opacity = Math.max(0, 1 - this.age / this.life)
    return this.age < this.life
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.points)
    this.points.geometry.dispose()
    ;(this.points.material as THREE.Material).dispose()
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
      new ParticleBurst(scene, glow, origin, { count: 900, color: 0xffe3b4, spread: 1.5, speed: 20, size: 0.26, life: 3.6, gravity: 5.4, drag: 0.975 }),
      new ParticleBurst(scene, glow, origin, { count: 420, color: 0xff9a4c, spread: 1.2, speed: 14, size: 0.32, life: 3.2, gravity: 4.2, drag: 0.98 }),
    ]
    // A bright core so the burst reads as molten iron, not a distant firework.
    this.core = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glow, color: 0xffe6b8, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending }),
    )
    this.core.position.copy(origin)
    this.core.scale.setScalar(2.4)
    scene.add(this.core)
    this.light = new THREE.PointLight(0xffb066, 55, 55, 2)
    this.light.position.copy(origin)
    scene.add(this.light)
    this.halo = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glow, color: 0xffb877, transparent: true, opacity: 0.22, depthWrite: false, blending: THREE.AdditiveBlending }),
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
    this.bursts.forEach((b) => b.dispose(scene))
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
    const mat = new THREE.MeshBasicMaterial({ color: 0xffc98a, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false })
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
    ;(this.mesh.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 0.8 * (1 - this.age / 2.2))
    return this.age < 2.2
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.mesh)
    this.mesh.geometry.dispose()
    ;(this.mesh.material as THREE.Material).dispose()
  }
}
