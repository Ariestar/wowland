import * as THREE from 'three'

/**
 * G0 cat-play prototype (PRD §8).
 *
 * Placeholder geometry only: a low-poly cat, a tipped basket, six tangerines
 * and a 1.2 m shed.  The purpose is to verify interaction, third-person
 * control, assisted jump and safe exit before real assets exist.  Everything
 * lives in Blender coordinates (x, y ground plane) and is converted to game
 * space (x, y-up, z = -y) for rendering.
 */

export type CatAction = 'idle' | 'walk' | 'pounce' | 'jump' | 'descend'

export type CatEvents = {
  onBasketTipped: () => void
  onShedLanded: () => void
  onActionChange: (action: CatAction) => void
}

export type CatZone = {
  minX: number
  maxX: number
  minY: number
  maxY: number
  spawn: { x: number; y: number }
  basket: { x: number; y: number }
  shed: { x: number; y: number; height: number }
  pawPrint: { x: number; y: number }
  walkSpeed: number
  pounceRange: number
  jumpRange: number
}

const CAT_HEIGHT = 0.34
const TANGERINE_COUNT = 6

/** Convert Blender (x, y) to game-space (x, z). */
const toGame = (x: number, y: number): [number, number] => [x, -y]

export class CatPrototype {
  readonly group = new THREE.Group()
  private readonly cat = new THREE.Group()
  private readonly catBody: THREE.Mesh
  private readonly catTail: THREE.Mesh
  private readonly basket = new THREE.Group()
  private readonly tangerines: { mesh: THREE.Mesh; vx: number; vz: number; active: boolean }[] = []
  private readonly shed: THREE.Mesh
  private readonly pawPrint: THREE.Mesh
  private readonly zone: CatZone
  private readonly events: CatEvents
  private readonly groundZ: number

  private pos = new THREE.Vector3()
  private yaw = 0
  private action: CatAction = 'idle'
  private actionT = 0
  private basketTipped = false
  private onShed = false
  private shedLandT = 0
  private jumpFrom = new THREE.Vector3()
  private jumpTo = new THREE.Vector3()
  private time = 0
  private moveInput = { f: 0, r: 0 }

  constructor(zone: CatZone, groundZ: number, events: CatEvents) {
    this.zone = zone
    this.groundZ = groundZ
    this.events = events

    // --- cat: body + head + ears + tail, all warm grey against the night.
    const fur = new THREE.MeshStandardMaterial({ color: 0x6b5a4e, roughness: 0.9 })
    const dark = new THREE.MeshStandardMaterial({ color: 0x3d332c, roughness: 0.9 })
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.26, 4, 8), fur)
    body.rotation.z = Math.PI / 2
    body.position.y = 0.16
    this.catBody = body
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.09, 10, 8), fur)
    head.position.set(0.24, 0.22, 0)
    const earGeo = new THREE.ConeGeometry(0.035, 0.07, 4)
    const earL = new THREE.Mesh(earGeo, dark)
    earL.position.set(0.26, 0.32, 0.05)
    const earR = new THREE.Mesh(earGeo, dark)
    earR.position.set(0.26, 0.32, -0.05)
    const tail = new THREE.Mesh(new THREE.CapsuleGeometry(0.022, 0.22, 3, 6), dark)
    tail.position.set(-0.24, 0.26, 0)
    tail.rotation.z = 0.9
    this.catTail = tail
    this.cat.add(body, head, earL, earR, tail)
    this.cat.traverse((o) => {
      o.castShadow = true
    })
    this.group.add(this.cat)

    // --- basket: open cylinder that tips on pounce.
    const bamboo = new THREE.MeshStandardMaterial({ color: 0xa8834f, roughness: 0.85 })
    const basketMesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.3, 0.24, 0.55, 12, 1, true),
      bamboo,
    )
    basketMesh.position.y = 0.275
    const basketBottom = new THREE.Mesh(new THREE.CircleGeometry(0.24, 12), bamboo)
    basketBottom.rotation.x = -Math.PI / 2
    basketBottom.position.y = 0.01
    this.basket.add(basketMesh, basketBottom)
    this.basket.traverse((o) => {
      o.castShadow = true
    })
    const [bx, bz] = toGame(zone.basket.x, zone.basket.y)
    this.basket.position.set(bx, groundZ, bz)
    // Lean against an invisible stool, per PRD §8.2.
    this.basket.rotation.z = 0.16
    this.group.add(this.basket)

    // --- tangerines hidden inside until the tip.
    const tangMat = new THREE.MeshStandardMaterial({
      color: 0xe8862e,
      roughness: 0.6,
      emissive: 0x401c02,
    })
    for (let i = 0; i < TANGERINE_COUNT; i++) {
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 6), tangMat)
      mesh.castShadow = true
      mesh.visible = false
      this.group.add(mesh)
      this.tangerines.push({ mesh, vx: 0, vz: 0, active: false })
    }

    // --- shed: a 1.5 × 1.5 m landing 1.2 m up.
    const wood = new THREE.MeshStandardMaterial({ color: 0x5c4632, roughness: 0.9 })
    this.shed = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.12, 1.6), wood)
    const [sx, sz] = toGame(zone.shed.x, zone.shed.y)
    this.shed.position.set(sx, groundZ + zone.shed.height, sz)
    this.shed.castShadow = true
    this.shed.receiveShadow = true
    const legGeo = new THREE.BoxGeometry(0.09, zone.shed.height, 0.09)
    for (const [lx, lz] of [
      [-0.7, -0.7],
      [0.7, -0.7],
      [-0.7, 0.7],
      [0.7, 0.7],
    ] as const) {
      const leg = new THREE.Mesh(legGeo, wood)
      leg.position.set(sx + lx, groundZ + zone.shed.height / 2, sz + lz)
      leg.castShadow = true
      this.group.add(leg)
    }
    this.group.add(this.shed)

    // --- paw print: the jump marker, bright only after the basket tips.
    const printMat = new THREE.MeshBasicMaterial({
      color: 0xffc477,
      transparent: true,
      opacity: 0.14,
      depthWrite: false,
    })
    this.pawPrint = new THREE.Mesh(new THREE.CircleGeometry(0.32, 20), printMat)
    const [px, pz] = toGame(zone.pawPrint.x, zone.pawPrint.y)
    this.pawPrint.rotation.x = -Math.PI / 2
    this.pawPrint.position.set(px, groundZ + 0.03, pz)
    this.group.add(this.pawPrint)

    this.reset()
  }

  /** Reset the attempt: cat at P07, basket upright, tangerines hidden. */
  reset() {
    const [x, z] = toGame(this.zone.spawn.x, this.zone.spawn.y)
    this.pos.set(x, this.groundZ, z)
    // Face the basket: yaw measures the game-space heading (dz, dx).
    this.yaw = Math.atan2(
      -(this.zone.basket.y - this.zone.spawn.y),
      this.zone.basket.x - this.zone.spawn.x,
    )
    this.action = 'idle'
    this.actionT = 0
    this.basketTipped = false
    this.onShed = false
    const [bx, bz] = toGame(this.zone.basket.x, this.zone.basket.y)
    this.basket.position.set(bx, this.groundZ, bz)
    this.basket.rotation.set(0, 0, 0.16)
    for (const t of this.tangerines) {
      t.active = false
      t.mesh.visible = false
    }
    ;(this.pawPrint.material as THREE.MeshBasicMaterial).opacity = 0.14
    this.applyTransform()
    this.setMove(0, 0)
  }

  setMove(f: number, r: number) {
    this.moveInput.f = f
    this.moveInput.r = r
  }

  /** Snap the heading (tests and assisted steering). */
  face(yaw: number) {
    this.yaw = yaw
  }

  /** Player pressed the action button; the scene decides which move applies. */
  act(): void {
    if (this.action === 'pounce' || this.action === 'jump' || this.action === 'descend') return
    if (this.onShed) {
      this.startDescend()
      return
    }
    if (!this.basketTipped && this.nearBasket()) {
      this.startPounce()
      return
    }
    if (this.basketTipped && this.nearPawPrint()) {
      this.startJump()
      return
    }
    // A light hop so the press never feels dead (PRD §8.7).
    this.action = 'pounce'
    this.actionT = 0
    this.events.onActionChange(this.action)
  }

  private nearBasket(): boolean {
    const [bx, bz] = toGame(this.zone.basket.x, this.zone.basket.y)
    return Math.hypot(this.pos.x - bx, this.pos.z - bz) < this.zone.pounceRange
  }

  private nearPawPrint(): boolean {
    const [px, pz] = toGame(this.zone.pawPrint.x, this.zone.pawPrint.y)
    return Math.hypot(this.pos.x - px, this.pos.z - pz) < this.zone.jumpRange
  }

  private startPounce() {
    this.action = 'pounce'
    this.actionT = 0
    this.events.onActionChange(this.action)
  }

  private startJump() {
    this.action = 'jump'
    this.actionT = 0
    this.jumpFrom.copy(this.pos)
    const [sx, sz] = toGame(this.zone.shed.x, this.zone.shed.y)
    this.jumpTo.set(sx, this.groundZ + this.zone.shed.height + 0.06, sz)
    this.events.onActionChange(this.action)
  }

  private startDescend() {
    this.action = 'descend'
    this.actionT = 0
    this.jumpFrom.copy(this.pos)
    const [px, pz] = toGame(this.zone.pawPrint.x, this.zone.pawPrint.y)
    this.jumpTo.set(px, this.groundZ, pz)
    this.events.onActionChange(this.action)
  }

  update(dt: number) {
    this.time += dt
    this.actionT += dt

    switch (this.action) {
      case 'idle':
      case 'walk': {
        const { f, r } = this.moveInput
        if (f || r) {
          const len = Math.hypot(f, r) || 1
          const fx = Math.cos(this.yaw)
          const fz = Math.sin(this.yaw)
          const rx = -Math.sin(this.yaw)
          const rz = Math.cos(this.yaw)
          const dx = ((f * fx + r * rx) / len) * this.zone.walkSpeed * dt
          const dz = ((f * fz + r * rz) / len) * this.zone.walkSpeed * dt
          const nx = THREE.MathUtils.clamp(this.pos.x + dx, this.zone.minX, this.zone.maxX)
          const nz = THREE.MathUtils.clamp(this.pos.z + dz, -this.zone.maxY, -this.zone.minY)
          if (nx !== this.pos.x || nz !== this.pos.z) {
            this.pos.x = nx
            this.pos.z = nz
            if (this.action !== 'walk') {
              this.action = 'walk'
              this.events.onActionChange(this.action)
            }
          }
          // Face the movement direction smoothly.
          const target = Math.atan2(dz, dx)
          let d = target - this.yaw
          while (d > Math.PI) d -= Math.PI * 2
          while (d < -Math.PI) d += Math.PI * 2
          this.yaw += d * Math.min(1, dt * 10)
        } else if (this.action !== 'idle') {
          this.action = 'idle'
          this.events.onActionChange(this.action)
        }
        // Breathing and tail sway keep the placeholder readable.
        this.catBody.scale.y = 1 + Math.sin(this.time * 2.4) * 0.03
        this.catTail.rotation.y = Math.sin(this.time * 3.1) * 0.4
        break
      }
      case 'pounce': {
        // 0.55 s lunge; the basket tips at the midpoint when in range.
        const t = Math.min(1, this.actionT / 0.55)
        const lunge = Math.sin(t * Math.PI) * 0.42
        this.cat.position.z = 0
        this.cat.position.x = lunge
        this.cat.position.y = Math.sin(t * Math.PI) * 0.1
        if (t >= 0.5 && !this.basketTipped && this.nearBasket()) this.tipBasket()
        if (t >= 1) {
          this.cat.position.set(0, 0, 0)
          this.action = 'idle'
          this.events.onActionChange(this.action)
        }
        break
      }
      case 'jump': {
        const t = Math.min(1, this.actionT / 0.7)
        const e = t * t * (3 - 2 * t)
        this.pos.lerpVectors(this.jumpFrom, this.jumpTo, e)
        this.pos.y =
          this.jumpFrom.y + (this.jumpTo.y - this.jumpFrom.y) * e + Math.sin(t * Math.PI) * 0.5
        if (t >= 1) {
          this.pos.copy(this.jumpTo)
          this.onShed = true
          this.shedLandT = 0
          this.action = 'idle'
          this.events.onActionChange(this.action)
          this.events.onShedLanded()
        }
        break
      }
      case 'descend': {
        const t = Math.min(1, this.actionT / 0.7)
        const e = t * t * (3 - 2 * t)
        this.pos.lerpVectors(this.jumpFrom, this.jumpTo, e)
        this.pos.y =
          this.jumpFrom.y + (this.jumpTo.y - this.jumpFrom.y) * e + Math.sin(t * Math.PI) * 0.35
        if (t >= 1) {
          this.pos.copy(this.jumpTo)
          this.onShed = false
          this.action = 'idle'
          this.events.onActionChange(this.action)
        }
        break
      }
    }

    if (this.onShed) this.shedLandT += dt

    // Tangerines roll out in a bounded 3 × 3 m patch and settle.
    for (const tang of this.tangerines) {
      if (!tang.active) continue
      tang.mesh.position.x += tang.vx * dt
      tang.mesh.position.z += tang.vz * dt
      tang.vx *= 1 - Math.min(1, dt * 1.6)
      tang.vz *= 1 - Math.min(1, dt * 1.6)
      tang.mesh.rotation.x += tang.vz * dt * 8
      tang.mesh.rotation.z -= tang.vx * dt * 8
      const [bx, bz] = toGame(this.zone.basket.x, this.zone.basket.y)
      if (Math.abs(tang.mesh.position.x - bx) > 1.5) tang.vx *= -0.4
      if (Math.abs(tang.mesh.position.z - bz) > 1.5) tang.vz *= -0.4
    }

    // The paw print breathes once the jump step is live.
    if (this.basketTipped && !this.onShed) {
      ;(this.pawPrint.material as THREE.MeshBasicMaterial).opacity =
        0.35 + Math.sin(this.time * 3) * 0.15
    }

    this.applyTransform()
  }

  private tipBasket() {
    this.basketTipped = true
    this.basket.rotation.z = Math.PI / 2 + 0.12
    this.basket.position.y = this.groundZ + 0.05
    const [bx, bz] = toGame(this.zone.basket.x, this.zone.basket.y)
    for (let i = 0; i < this.tangerines.length; i++) {
      const tang = this.tangerines[i]
      tang.active = true
      tang.mesh.visible = true
      const angle = (i / this.tangerines.length) * Math.PI * 2 + Math.random() * 0.6
      const speed = 0.7 + Math.random() * 0.7
      tang.mesh.position.set(bx + Math.random() * 0.2, this.groundZ + 0.06, bz)
      tang.vx = Math.cos(angle) * speed
      tang.vz = Math.sin(angle) * speed
    }
    this.events.onBasketTipped()
  }

  private applyTransform() {
    this.cat.position.set(this.pos.x, this.pos.y, this.pos.z)
    this.cat.rotation.y = -this.yaw + Math.PI / 2
  }

  /** Where the camera should sit to keep cat and target in frame. */
  cameraTarget(out: THREE.Vector3, yawOut: { yaw: number; pitch: number }) {
    const back = 2.6
    const cx = this.pos.x - Math.cos(this.yaw) * back
    const cz = this.pos.z - Math.sin(this.yaw) * back
    out.set(cx, Math.max(this.groundZ + 1.1, this.pos.y + 1.15), cz)
    yawOut.yaw = this.yaw
    yawOut.pitch = -0.24
  }

  get isBusy(): boolean {
    return this.action === 'pounce' || this.action === 'jump' || this.action === 'descend'
  }

  /** The cat's ground position in game space. */
  get position(): THREE.Vector3 {
    return this.pos
  }

  get tipped(): boolean {
    return this.basketTipped
  }

  get landed(): boolean {
    return this.onShed
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.group)
    this.group.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (mesh.isMesh) {
        mesh.geometry.dispose()
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const m of mats) m.dispose()
      }
    })
  }
}

export const CAT_GROUND_OFFSET = CAT_HEIGHT
