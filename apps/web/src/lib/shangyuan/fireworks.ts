import * as THREE from 'three'
import type { Effect } from './effects'

/**
 * GPU fireworks.
 *
 * Every spark is one instance of a camera-facing quad whose whole flight —
 * drag, gravity, streak stretch, twinkle, cooling from white to its shell
 * colour — is evaluated in the vertex shader from `uTime`.  A burst is a
 * write into a ring buffer, so a shell costs one draw call and no per-frame
 * CPU work, and the streaks read as real comets instead of round dots.
 */

export type ShellKind =
  | 'peony'
  | 'chrysanthemum'
  | 'willow'
  | 'ring'
  | 'palm'
  | 'double'
  | 'glitter'

export interface ShellOptions {
  kind?: ShellKind
  color?: THREE.ColorRepresentation
  accent?: THREE.ColorRepresentation
  /** Burst radius in metres. */
  radius?: number
  /** Seconds the sparks burn. */
  life?: number
  /** Spark count. */
  count?: number
}

const TAU = Math.PI * 2
const CAPACITY = 9000

const VERTEX_SHADER = /* glsl */ `
  attribute vec3 aOrigin;
  attribute vec3 aVelocity;
  attribute vec3 aColor;
  attribute float aStart;
  attribute float aLife;
  attribute float aDrag;
  attribute float aGravity;
  attribute float aSize;
  attribute float aSeed;
  attribute float aFlags;

  uniform float uTime;
  uniform float uBaseSize;
  uniform float uStretch;
  uniform float uMaxStretch;
  uniform float uIntensity;
  uniform float uRefDistance;
  uniform float uMaxScale;

  varying vec3 vColor;
  varying vec2 vUv;
  varying vec2 vSpan;
  varying float vAlpha;
  varying float vHeat;

  void main() {
    float age = uTime - aStart;
    float t = age / max(aLife, 0.0001);
    if (age < 0.0 || t > 1.0) {
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      vColor = vec3(0.0);
      vAlpha = 0.0;
      vHeat = 0.0;
      vUv = vec2(0.5);
      vSpan = vec2(1.0);
      return;
    }

    // Closed-form linear drag: the spark sheds speed fast at birth and then
    // coasts, which is what gives a shell its dense core and loose skirt.
    float k = max(aDrag, 0.0001);
    float damp = exp(-k * age);
    float travel = (1.0 - damp) / k;
    vec3 pos = aOrigin + aVelocity * travel
             + vec3(0.0, -0.5 * aGravity * age * age, 0.0);
    vec3 vel = aVelocity * damp + vec3(0.0, -aGravity * age, 0.0);

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    vec2 dir = (viewMatrix * vec4(vel, 0.0)).xy;
    float speed = length(dir);
    dir = speed > 0.0001 ? dir / speed : vec2(0.0, 1.0);
    vec2 perp = vec2(-dir.y, dir.x);

    float fadeIn = smoothstep(0.0, 0.03, t);
    float fadeOut = 1.0 - smoothstep(0.60, 1.0, t);
    float twinkle = 1.0;
    if (aFlags > 0.5) {
      float wave = 0.5 + 0.5 * sin(age * 44.0 + aSeed * 61.0);
      twinkle = 1.0 - smoothstep(0.28, 0.60, t) * wave * 0.8;
    }
    vAlpha = fadeIn * fadeOut * twinkle * uIntensity;
    vHeat = 1.0 - smoothstep(0.0, 0.18, t);

    // The quad trails behind the head along the screen-space velocity.  Size
    // grows with distance so a shell 200 m away keeps the same on-screen
    // weight as a near spark, and the trail grows only as its square root so
    // far shells do not turn into ribbons.
    float dist = max(-mv.z, 1.0);
    float scale = clamp(dist / uRefDistance, 1.0, uMaxScale);
    float head = uBaseSize * aSize * scale;
    float tail = min(speed * uStretch, uMaxStretch) * aSize * sqrt(scale);
    // The quad runs from the tail tip to the leading edge of the head, so the
    // hot cap is not cut in half by the quad's own top edge.
    float span = tail + head * 0.5;
    float along = (position.y + 0.5) * span - tail;
    mv.xy += dir * along + perp * position.x * head;

    gl_Position = projectionMatrix * mv;
    vUv = uv;
    vSpan = vec2(span, head);
    vColor = aColor;
  }
`

const FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying vec2 vUv;
  varying vec2 vSpan;
  varying float vAlpha;
  varying float vHeat;

  void main() {
    // Head-local coordinates in view units, so the cap stays a true circle
    // however long the streak behind it is.
    vec2 p = vec2((vUv.x - 0.5) * vSpan.y,
                  (vUv.y - 1.0) * vSpan.x + vSpan.y * 0.5);
    float rHead = length(p) / max(vSpan.y * 0.5, 0.0001);

    float halo = 1.0 - smoothstep(0.0, 1.0, rHead);
    halo *= halo;
    float core = 1.0 - smoothstep(0.0, 0.52, rHead);
    core *= core;

    // The trail is a wedge that narrows from the head to the tail tip, so a
    // fast spark reads as a comet instead of a smeared rectangle.
    float across = abs(vUv.x - 0.5) * 2.0;
    float wedge = smoothstep(0.0, 0.82, vUv.y);
    float band = 1.0 - smoothstep(0.0, 1.0, across / max(wedge, 0.001));
    band *= band;
    float fade = smoothstep(0.0, 0.92, vUv.y);
    fade *= fade;

    float energy = halo * 0.70 + core * 1.45 + band * fade * 0.80;
    vec3 col = mix(vColor, vec3(1.0), clamp(core * 0.95 + vHeat * 0.6, 0.0, 1.0));
    gl_FragColor = vec4(col * energy * vAlpha, 1.0);
  }
`

let shockwaveMap: THREE.Texture | null = null

function shockwaveTexture() {
  if (shockwaveMap) return shockwaveMap
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    const gradient = ctx.createRadialGradient(
      size / 2,
      size / 2,
      size * 0.3,
      size / 2,
      size / 2,
      size * 0.5,
    )
    gradient.addColorStop(0, 'rgba(255,255,255,0)')
    gradient.addColorStop(0.55, 'rgba(255,255,255,0.05)')
    gradient.addColorStop(0.84, 'rgba(255,255,255,0.85)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
  }
  shockwaveMap = new THREE.CanvasTexture(canvas)
  shockwaveMap.colorSpace = THREE.SRGBColorSpace
  return shockwaveMap
}

export class FireworkSystem {
  readonly object: THREE.Mesh
  readonly glow: THREE.Texture

  private readonly geometry: THREE.InstancedBufferGeometry
  private readonly material: THREE.ShaderMaterial
  private readonly origins = new Float32Array(CAPACITY * 3)
  private readonly velocities = new Float32Array(CAPACITY * 3)
  private readonly colors = new Float32Array(CAPACITY * 3)
  private readonly starts = new Float32Array(CAPACITY)
  private readonly lives = new Float32Array(CAPACITY)
  private readonly drags = new Float32Array(CAPACITY)
  private readonly gravities = new Float32Array(CAPACITY)
  private readonly sizes = new Float32Array(CAPACITY)
  private readonly seeds = new Float32Array(CAPACITY)
  private readonly flags = new Float32Array(CAPACITY)
  private readonly attributes: THREE.InstancedBufferAttribute[] = []
  private cursor = 0
  private clock = 0
  private dirty = false

  constructor(glow: THREE.Texture) {
    this.glow = glow

    const geometry = new THREE.InstancedBufferGeometry()
    geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(
        new Float32Array([-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0]),
        3,
      ),
    )
    geometry.setAttribute(
      'uv',
      new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2),
    )
    geometry.setIndex(new THREE.BufferAttribute(new Uint16Array([0, 1, 2, 0, 2, 3]), 1))
    geometry.instanceCount = CAPACITY

    const attach = (name: string, array: Float32Array, itemSize: number) => {
      const attribute = new THREE.InstancedBufferAttribute(array, itemSize)
      attribute.setUsage(THREE.DynamicDrawUsage)
      geometry.setAttribute(name, attribute)
      this.attributes.push(attribute)
    }
    attach('aOrigin', this.origins, 3)
    attach('aVelocity', this.velocities, 3)
    attach('aColor', this.colors, 3)
    attach('aStart', this.starts, 1)
    attach('aLife', this.lives, 1)
    attach('aDrag', this.drags, 1)
    attach('aGravity', this.gravities, 1)
    attach('aSize', this.sizes, 1)
    attach('aSeed', this.seeds, 1)
    attach('aFlags', this.flags, 1)

    this.material = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      uniforms: {
        uTime: { value: 0 },
        uBaseSize: { value: 0.5 },
        uStretch: { value: 0.115 },
        uMaxStretch: { value: 9.0 },
        uIntensity: { value: 1.5 },
        uRefDistance: { value: 40 },
        uMaxScale: { value: 6 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      // The quad's local axes are remapped into the screen-space streak frame,
      // which reverses its winding as the streak turns.
      side: THREE.DoubleSide,
    })

    this.geometry = geometry
    this.object = new THREE.Mesh(geometry, this.material)
    this.object.frustumCulled = false
    this.object.renderOrder = 4
    // Additive quads have no meaningful normal; keep them out of the GTAO
    // normal prepass or they punch square holes in the sky.
    this.object.userData.noGtao = true
  }

  update(dt: number) {
    this.clock += dt
    this.material.uniforms.uTime.value = this.clock
    if (this.dirty) {
      for (const attribute of this.attributes) attribute.needsUpdate = true
      this.dirty = false
    }
  }

  /** Current show clock, the reference every scheduled spark uses. */
  get time() {
    return this.clock
  }

  /** One spark, scheduled at an absolute clock time. */
  spark(
    x: number,
    y: number,
    z: number,
    vx: number,
    vy: number,
    vz: number,
    color: THREE.Color,
    start: number,
    life: number,
    drag: number,
    gravity: number,
    size: number,
    flags: number,
  ) {
    const i = this.cursor
    this.cursor = (this.cursor + 1) % CAPACITY
    const i3 = i * 3
    this.origins[i3] = x
    this.origins[i3 + 1] = y
    this.origins[i3 + 2] = z
    this.velocities[i3] = vx
    this.velocities[i3 + 1] = vy
    this.velocities[i3 + 2] = vz
    this.colors[i3] = color.r
    this.colors[i3 + 1] = color.g
    this.colors[i3 + 2] = color.b
    this.starts[i] = start
    this.lives[i] = life
    this.drags[i] = drag
    this.gravities[i] = gravity
    this.sizes[i] = size
    this.seeds[i] = Math.random()
    this.flags[i] = flags
    this.dirty = true
  }

  /** Schedule a burst, optionally `offset` seconds in the future. */
  burst(origin: THREE.Vector3, options: ShellOptions = {}, offset = 0) {
    const kind = options.kind ?? 'peony'
    const radius = options.radius ?? 26
    const life = options.life ?? 2.7
    const count = options.count ?? 560
    const primary = new THREE.Color(options.color ?? 0xffc07a)
    const accent = new THREE.Color(options.accent ?? options.color ?? 0xffe3b4)
    const start = this.clock + offset
    const speed = radius * 1.38

    const emit = (
      vx: number,
      vy: number,
      vz: number,
      color: THREE.Color,
      sparkLife: number,
      drag: number,
      gravity: number,
      size: number,
      flags: number,
    ) => {
      this.spark(
        origin.x,
        origin.y,
        origin.z,
        vx,
        vy,
        vz,
        color,
        start,
        sparkLife,
        drag,
        gravity,
        size,
        flags,
      )
    }

    const sphere = (
      n: number,
      scale: number,
      color: THREE.Color,
      lifeScale: number,
      sizeScale: number,
      drag: number,
      gravity: number,
      twinkleChance: number,
    ) => {
      for (let i = 0; i < n; i++) {
        const y = Math.random() * 2 - 1
        const a = Math.random() * TAU
        const r = Math.sqrt(Math.max(0, 1 - y * y))
        const sp = speed * scale * (0.9 + Math.random() * 0.16)
        emit(
          r * Math.cos(a) * sp,
          y * sp,
          r * Math.sin(a) * sp,
          Math.random() < 0.14 ? accent : color,
          life * lifeScale * (0.82 + Math.random() * 0.3),
          drag * (0.92 + Math.random() * 0.2),
          gravity,
          sizeScale * (0.85 + Math.random() * 0.4),
          Math.random() < twinkleChance ? 1 : 0,
        )
      }
    }

    if (kind === 'peony') {
      sphere(count, 1.0, primary, 1.0, 1.0, 0.85, 2.3, 0.08)
    } else if (kind === 'chrysanthemum') {
      sphere(count, 1.0, primary, 1.32, 0.78, 1.45, 2.7, 0.16)
    } else if (kind === 'glitter') {
      sphere(count, 1.0, primary, 1.5, 0.7, 1.05, 2.0, 0.85)
    } else if (kind === 'willow') {
      for (let i = 0; i < count; i++) {
        const y = -0.3 - Math.random() * 0.7
        const a = Math.random() * TAU
        const r = Math.sqrt(Math.max(0, 1 - y * y))
        const sp = speed * (0.48 + Math.random() * 0.52)
        emit(
          r * Math.cos(a) * sp,
          y * sp,
          r * Math.sin(a) * sp,
          Math.random() < 0.12 ? accent : primary,
          life * 1.9 * (0.8 + Math.random() * 0.4),
          1.75,
          1.15,
          0.8 * (0.85 + Math.random() * 0.4),
          1,
        )
      }
    } else if (kind === 'ring') {
      for (let i = 0; i < count; i++) {
        const a = Math.random() * TAU
        const rr = 0.96 + Math.random() * 0.08
        emit(
          Math.cos(a) * speed * rr,
          Math.sin(a) * speed * rr,
          (Math.random() - 0.5) * speed * 0.05,
          Math.random() < 0.2 ? accent : primary,
          life * (0.85 + Math.random() * 0.3),
          0.9,
          2.1,
          0.9 * (0.85 + Math.random() * 0.35),
          Math.random() < 0.1 ? 1 : 0,
        )
      }
    } else if (kind === 'palm') {
      const fronds = 11
      const per = Math.max(1, Math.floor(count / fronds))
      for (let f = 0; f < fronds; f++) {
        const y = 0.25 + Math.random() * 0.75
        const a = Math.random() * TAU
        const r = Math.sqrt(Math.max(0, 1 - y * y))
        const bx = r * Math.cos(a)
        const bz = r * Math.sin(a)
        for (let i = 0; i < per; i++) {
          // A frond is a stream, not a point: sparks spread along its axis and
          // fan slightly.  Sharing one velocity turns 56 sparks into a single
          // additive disc that blooms into a white blob.
          const along = 0.52 + (i / per) * 0.48
          const fan = 0.055
          emit(
            (bx * along + (Math.random() - 0.5) * fan) * speed,
            (y * along + (Math.random() - 0.5) * fan) * speed,
            (bz * along + (Math.random() - 0.5) * fan) * speed,
            Math.random() < 0.18 ? accent : primary,
            life * (0.85 + Math.random() * 0.3),
            0.95,
            2.6,
            1.25 * (0.85 + Math.random() * 0.4),
            0,
          )
        }
      }
    } else {
      // double: a small hot inner shell inside the main one.
      sphere(Math.floor(count * 0.62), 1.0, primary, 1.0, 1.0, 0.9, 2.3, 0.1)
      sphere(Math.floor(count * 0.38), 0.48, accent, 1.2, 0.8, 1.2, 2.0, 0.3)
    }
  }

  dispose() {
    this.geometry.dispose()
    this.material.dispose()
  }
}

export interface ShellLaunch {
  /** Ground point the shell lifts from. Omit for a silent sky burst. */
  from?: THREE.Vector3
  to: THREE.Vector3
  ascent?: number
  kind?: ShellKind
  color?: THREE.ColorRepresentation
  accent?: THREE.ColorRepresentation
  radius?: number
  life?: number
  count?: number
  /** Scale of the burst flash and shockwave. */
  flash?: number
  onLaunch?: () => void
  onBurst?: () => void
}

/** A rising shell, its trail, its burst and the flash around it. */
export class FireworkShell implements Effect {
  private readonly flash: THREE.Sprite
  private readonly shock: THREE.Sprite
  private readonly smoke: THREE.Sprite[] = []
  private readonly ascent: number
  private readonly burstLife: number
  private readonly flashScale: number
  private readonly radius: number
  private age = 0
  private bursted = false

  constructor(scene: THREE.Scene, system: FireworkSystem, launch: ShellLaunch) {
    this.ascent = launch.from ? (launch.ascent ?? 1.05) : 0
    this.burstLife = Math.max(2.6, (launch.life ?? 2.7) * 1.05)
    this.flashScale = launch.flash ?? 1
    this.radius = launch.radius ?? 26

    const to = launch.to
    if (launch.from && this.ascent > 0) {
      // Pre-schedule the whole ascent.  The trail is drawn by the same
      // instanced pool, so a launch costs nothing per frame.
      const from = launch.from
      const steps = Math.max(8, Math.round(this.ascent / 0.02))
      const warm = new THREE.Color(0xffcf92)
      for (let i = 0; i <= steps; i++) {
        const u = i / steps
        const ease = u * (1.18 - 0.18 * u)
        const nextU = Math.min(1, u + 1 / steps)
        const nextEase = nextU * (1.18 - 0.18 * nextU)
        const dt = this.ascent / steps
        system.spark(
          from.x + (to.x - from.x) * ease,
          from.y + (to.y - from.y) * ease,
          from.z + (to.z - from.z) * ease,
          ((to.x - from.x) * (nextEase - ease)) / dt,
          ((to.y - from.y) * (nextEase - ease)) / dt,
          ((to.z - from.z) * (nextEase - ease)) / dt,
          warm,
          system.time + u * this.ascent,
          0.3,
          2.0,
          1.6,
          0.8,
          0,
        )
      }
      launch.onLaunch?.()
    }

    system.burst(
      to,
      {
        kind: launch.kind,
        color: launch.color,
        accent: launch.accent,
        radius: launch.radius,
        life: launch.life,
        count: launch.count,
      },
      this.ascent,
    )

    const tint = new THREE.Color(launch.color ?? 0xffc07a)
    this.flash = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: system.glow,
        color: tint.clone().lerp(new THREE.Color(0xffffff), 0.5),
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    this.flash.position.copy(to)
    this.flash.scale.setScalar(1)
    this.flash.visible = false
    scene.add(this.flash)

    this.shock = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: shockwaveTexture(),
        color: tint,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    this.shock.position.copy(to)
    this.shock.scale.setScalar(1)
    this.shock.visible = false
    scene.add(this.shock)

    for (let i = 0; i < 5; i++) {
      const puff = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: system.glow,
          color: 0x6b5a48,
          transparent: true,
          opacity: 0,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      )
      const spread = this.radius * 0.22
      puff.position.set(
        to.x + (Math.random() - 0.5) * spread,
        to.y + (Math.random() - 0.5) * spread,
        to.z + (Math.random() - 0.5) * spread,
      )
      puff.visible = false
      scene.add(puff)
      this.smoke.push(puff)
    }
  }

  update(dt: number) {
    this.age += dt
    if (!this.bursted) {
      if (this.age < this.ascent) return true
      this.bursted = true
      this.flash.visible = true
      this.shock.visible = true
      for (const puff of this.smoke) puff.visible = true
    }

    const t = this.age - this.ascent

    const fk = Math.min(1, t / 0.32)
    this.flash.scale.setScalar(this.flashScale * (0.4 + fk * 2.6) * this.radius * 0.16)
    this.flash.material.opacity = 0.95 * (1 - fk)
    this.flash.visible = fk < 1

    const sk = Math.min(1, t / 0.62)
    this.shock.scale.setScalar(this.radius * (0.22 + sk * 2.35))
    this.shock.material.opacity = 0.5 * (1 - sk) ** 1.6
    this.shock.visible = sk < 1

    const mk = Math.min(1, t / 2.4)
    for (const puff of this.smoke) {
      puff.scale.setScalar(2.4 + mk * this.radius * 0.4)
      puff.material.opacity = 0.11 * (1 - mk)
    }

    return t < this.burstLife
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.flash)
    scene.remove(this.shock)
    this.flash.material.dispose()
    this.shock.material.dispose()
    for (const puff of this.smoke) {
      scene.remove(puff)
      puff.material.dispose()
    }
  }
}

/** A high throw of molten iron that breaks into falling gold sparks. */
export class IronFlower implements Effect {
  private readonly light: THREE.PointLight
  private readonly halo: THREE.Sprite
  private readonly core: THREE.Sprite
  private readonly life = 3.6
  private age = 0

  constructor(scene: THREE.Scene, system: FireworkSystem, origin: THREE.Vector3) {
    // A fast white-gold spray with a slower orange skirt underneath.
    system.burst(origin, {
      kind: 'palm',
      color: 0xfff2d8,
      accent: 0xffb066,
      radius: 30,
      life: 3.0,
      count: 620,
    })
    system.burst(origin, {
      kind: 'glitter',
      color: 0xff9a4c,
      accent: 0xffe0b0,
      radius: 17,
      life: 3.4,
      count: 360,
    })

    this.core = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: system.glow,
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
        map: system.glow,
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
    this.light.intensity = Math.max(0, 55 * (1 - this.age / this.life))
    this.core.scale.setScalar(2.4 + this.age * 2.2)
    this.core.material.opacity = Math.max(0, 0.95 - this.age / 0.5)
    this.halo.scale.setScalar(3 + this.age * 0.9)
    this.halo.material.opacity = Math.max(0, 0.22 * (1 - this.age / 2))
    return this.age < this.life
  }

  dispose(scene: THREE.Scene) {
    scene.remove(this.light)
    scene.remove(this.halo)
    scene.remove(this.core)
    this.halo.material.dispose()
    this.core.material.dispose()
  }
}
