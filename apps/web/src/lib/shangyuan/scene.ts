import * as THREE from 'three'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js'
import { SMAAPass } from 'three/addons/postprocessing/SMAAPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { ShangyuanAudio } from './audio'
import { type CollisionLayout, ObstacleField, WalkableGround } from './collision'
import {
  BLESSINGS,
  INTERACTABLES,
  type InteractableId,
  LANTERN_STYLES,
  RIDDLES,
  SCENE,
  VIEWPOINTS,
} from './data'
import { type Effect, IronFlower, ParticleBurst, Ripple, RiverAtmosphere } from './effects'
import { WaterlineFlora } from './flora'
import { gradingShader, sanitizeShader } from './postFx'
import type { Panel, Phase, SceneCallbacks } from './types'
import { batTexture, createWaterMaterial, glowTexture, skyLanternTexture } from './water'

const MODEL_BASE = '/models/lantern-river/'
const TEMPLATE_BASE = '/models/shangyuan/'
const EYE = 1.62
const SPEED = 3.6
const RUN = 6.2
const PLAYER_RADIUS = 0.32
const STEP_UP = 0.5
const STEP_DOWN = 1.2
/** Keep sub-steps shorter than the player radius so no obstacle can be tunnelled. */
const MAX_SUBSTEP = 0.28

/**
 * The mirrored world doubles the triangle count.  Phones and low-core machines
 * keep the shader-only water, which already carries lantern streaks and glints.
 */
function reflectionBudget(): boolean {
  if (window.matchMedia('(pointer: coarse)').matches) return false
  return (navigator.hardwareConcurrency ?? 8) >= 6
}

/**
 * Desktop machines get the sharper pipeline: the full device pixel ratio, a
 * 4K shadow map and post-process antialiasing.  Touch devices keep the lighter
 * settings that hold their frame budget.
 */
function highQuality(): boolean {
  if (window.matchMedia('(pointer: coarse)').matches) return false
  return (navigator.hardwareConcurrency ?? 8) >= 8
}

export class ShangyuanScene {
  private readonly canvas: HTMLCanvasElement
  private readonly cb: SceneCallbacks
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private readonly composer: EffectComposer
  private readonly bloom: UnrealBloomPass
  private readonly grading: ShaderPass
  private readonly atmosphere: RiverAtmosphere
  private flora: WaterlineFlora | null = null
  private readonly clock = new THREE.Clock()
  private readonly loader = new GLTFLoader()
  private readonly audio = new ShangyuanAudio()

  private readonly waterMat: THREE.ShaderMaterial
  private readonly water: THREE.Mesh
  private readonly highTier = highQuality()
  private readonly reflectionTarget: THREE.WebGLRenderTarget | null
  private readonly reflectionCamera = new THREE.PerspectiveCamera()
  private worldReady = false
  private shadowFrames = 0
  private shadowFrozen = false
  private reflectionTick = 0
  private environmentMap: THREE.Texture | null = null
  private readonly glow: THREE.Texture
  private readonly skyGlow: THREE.Texture
  private skyLanterns: {
    points: THREE.Points
    positions: Float32Array
    speeds: Float32Array
    phases: Float32Array
    drifts: Float32Array
  } | null = null
  private readonly towerGlow: THREE.Sprite[] = []
  private readonly wheelPivots: THREE.Object3D[] = []
  private readonly lanterns: {
    obj: THREE.Object3D
    halo: THREE.Sprite
    t: number
    speed: number
    lane: number
  }[] = []
  private readonly effects: Effect[] = []
  private readonly lanternTemplates = new Map<string, THREE.Object3D>()

  private player = new THREE.Vector3(16.2, SCENE.groundZ + EYE, 124)
  private playerGround: number = SCENE.groundZ
  private layout: CollisionLayout | null = null
  /** Canal half-width, replaced by layout.json once the level loads. */
  private riverHalf = 12.5
  private groundField: WalkableGround | null = null
  private obstacleField: ObstacleField | null = null
  private collisionDebug: THREE.Group | null = null
  private yaw = -1.75
  private pitch = 0
  private keys = new Set<string>()
  private dragging = false
  private lastPointer = { x: 0, y: 0 }
  private pointerLocked = false

  private phase: Phase = 'idle'
  private wicks = 0
  private riddleIndex = 0
  private riddlesSolved = 0
  private style = ''
  private blessing = ''
  private released = 0
  private showClock = -1
  private showStage = 0
  private autoShow = -1
  private nextFirework = 5
  private towerPulse = 0
  private nearby: InteractableId | null = null
  private panel: Panel | null = null
  private disposed = false
  private raf = 0
  private photo = false
  private pan: { yaw: number; pitch: number; t: number } | null = null
  private viewTween: {
    from: THREE.Vector3
    to: THREE.Vector3
    fromYaw: number
    toYaw: number
    fromPitch: number
    toPitch: number
    t: number
  } | null = null
  private idleClock = 0
  private touchMove = 0
  private touchStrafe = 0

  constructor(canvas: HTMLCanvasElement, callbacks: SceneCallbacks) {
    this.canvas = canvas
    this.cb = callbacks
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: 'high-performance',
    })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, this.highTier ? 2 : 1.75))
    this.renderer.toneMapping = THREE.AgXToneMapping
    this.renderer.toneMappingExposure = 0.7
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.info.autoReset = false

    const draco = new DRACOLoader()
    draco.setDecoderPath('/draco/')
    this.loader.setDRACOLoader(draco)

    this.camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1800)
    this.camera.position.copy(this.player)
    this.scene.fog = new THREE.FogExp2(0x070d20, 0.0013)

    this.glow = glowTexture()
    this.skyGlow = skyLanternTexture()
    this.waterMat = createWaterMaterial(reflectionBudget() ? 0.8 : 0.96)
    this.water = new THREE.Mesh(new THREE.PlaneGeometry(36, 380, 48, 320), this.waterMat)
    this.water.rotation.x = -Math.PI / 2
    this.water.position.set(0, 0.05, -20)
    // Draw before floating lanterns so its transparency never swallows them.
    this.water.renderOrder = -2
    this.scene.add(this.water)
    this.reflectionTarget = reflectionBudget()
      ? new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType })
      : null
    if (this.reflectionTarget) {
      this.waterMat.uniforms.uReflection.value = this.reflectionTarget.texture
    }

    this.atmosphere = new RiverAtmosphere(this.glow, batTexture())
    this.scene.add(this.atmosphere.object)

    this.composer = new EffectComposer(this.renderer)
    this.composer.addPass(new RenderPass(this.scene, this.camera))
    this.composer.addPass(new ShaderPass(sanitizeShader()))
    if (this.highTier) {
      // Ground contact is what the night lighting lacks most; a short-radius
      // GTAO pass darkens eaves, plinths and the base of every prop.
      const gtao = new GTAOPass(this.scene, this.camera, 1, 1)
      gtao.output = GTAOPass.OUTPUT.Default
      gtao.blendIntensity = 0.8
      gtao.updateGtaoMaterial({
        radius: 0.55,
        distanceExponent: 1.4,
        thickness: 1.2,
        scale: 1,
        samples: 16,
        distanceFallOff: 1,
        screenSpaceRadius: false,
      })
      gtao.updatePdMaterial({ radius: 5, rings: 2, samples: 12 })
      // The AO buffer is upscaled anyway, so rendering its depth/normal
      // prepass at half size removes a full-resolution scene pass.
      const setGtaoSize = gtao.setSize.bind(gtao)
      gtao.setSize = (width: number, height: number) => {
        setGtaoSize(Math.max(1, Math.round(width / 2)), Math.max(1, Math.round(height / 2)))
      }
      this.composer.addPass(gtao)
    }
    // A higher threshold keeps the lantern cores hot while the shoji walls stay
    // crisp; a low threshold turned the whole midground into warm haze.
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.5, 0.45, 0.9)
    this.composer.addPass(this.bloom)
    this.composer.addPass(new OutputPass())
    this.grading = new ShaderPass(gradingShader())
    this.composer.addPass(this.grading)
    // The composer draws through an offscreen target, so the canvas MSAA flag
    // never sees geometry edges.  SMAA cleans up the final graded image.
    if (this.highTier) this.composer.addPass(new SMAAPass())

    this.addEnvironment()
    this.addSky()
    this.addSkyLanterns()
    this.addLights()
    this.bindEvents()
    this.resize()
  }

  // ---------------------------------------------------------------- setup

  /**
   * A small procedural night sky, prefiltered into an environment map.  Without
   * it the metallic gold, lacquer and roof materials have nothing to reflect and
   * read as flat black cards.  The warm band at the horizon also matches the
   * light spilling off the lantern streets.
   */
  private addEnvironment() {
    const width = 1024
    const height = 512
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')!
    const grad = ctx.createLinearGradient(0, 0, 0, height)
    grad.addColorStop(0, '#01030c')
    grad.addColorStop(0.42, '#071434')
    grad.addColorStop(0.56, '#132a5a')
    grad.addColorStop(0.64, '#3b3a6d')
    grad.addColorStop(0.68, '#77485a')
    grad.addColorStop(0.74, '#1a1c34')
    grad.addColorStop(1, '#060a16')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, width, height)

    const rng = (() => {
      let seed = 20261118
      return () => {
        seed = (seed * 1664525 + 1013904223) % 4294967296
        return seed / 4294967296
      }
    })()

    // Warm lantern bokeh along the waterfront band.
    for (let i = 0; i < 64; i++) {
      const x = rng() * width
      const y = height * (0.6 + rng() * 0.09)
      const radius = 6 + rng() * 22
      const glow = ctx.createRadialGradient(x, y, 0, x, y, radius)
      glow.addColorStop(0, `rgba(255, 198, 126, ${0.5 + rng() * 0.4})`)
      glow.addColorStop(0.4, `rgba(255, 142, 72, ${0.22 + rng() * 0.18})`)
      glow.addColorStop(1, 'rgba(255, 120, 40, 0)')
      ctx.fillStyle = glow
      ctx.beginPath()
      ctx.arc(x, y, radius, 0, Math.PI * 2)
      ctx.fill()
    }

    // Moon: a small cold key reflected by water and roof tiles.
    const moonX = width * 0.36
    const moonY = height * 0.24
    const moon = ctx.createRadialGradient(moonX, moonY, 0, moonX, moonY, 52)
    moon.addColorStop(0, 'rgba(236, 244, 255, 1)')
    moon.addColorStop(0.16, 'rgba(196, 220, 255, 0.7)')
    moon.addColorStop(1, 'rgba(120, 160, 255, 0)')
    ctx.fillStyle = moon
    ctx.fillRect(moonX - 60, moonY - 60, 120, 120)

    const source = new THREE.CanvasTexture(canvas)
    source.mapping = THREE.EquirectangularReflectionMapping
    source.colorSpace = THREE.SRGBColorSpace
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.environmentMap = pmrem.fromEquirectangular(source).texture
    this.scene.environment = this.environmentMap
    // Enough for metal and lacquer to pick up the sky; low enough that the
    // rough plaster keeps its warm lamplight instead of turning moon-blue.
    this.scene.environmentIntensity = 0.28
    source.dispose()
    pmrem.dispose()
  }

  private addSky() {
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        uTop: { value: new THREE.Color('#050f33') },
        uMid: { value: new THREE.Color('#0a1d55') },
        uLow: { value: new THREE.Color('#1a3270') },
        uHaze: { value: new THREE.Color('#4b3f78') },
        uMoon: { value: new THREE.Vector3(-0.42, 0.52, 0.42).normalize() },
      },
      vertexShader: /* glsl */ `
        varying vec3 vDir;
        void main() {
          vDir = normalize(position);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uTop; uniform vec3 uMid; uniform vec3 uLow; uniform vec3 uHaze; uniform vec3 uMoon;
        varying vec3 vDir;
        void main() {
          float h = clamp(vDir.y, -1.0, 1.0);
          vec3 c = mix(uLow, uMid, smoothstep(-0.05, 0.3, h));
          c = mix(c, uTop, smoothstep(0.26, 0.9, h));
          // The festival sits under a low cobalt band: a cool horizon keeps the
          // sky from reading as flat black above a lantern-lit street.
          float band = exp(-pow((h - 0.06) * 5.5, 2.0));
          c += uHaze * band * 0.42;
          float warm = exp(-pow((h - 0.004) * 30.0, 2.0));
          c += vec3(0.22, 0.09, 0.1) * warm * 0.24;
          float d = max(dot(vDir, uMoon), 0.0);
          c += vec3(0.9, 0.95, 1.0) * pow(d, 620.0) * 0.9;
          c += vec3(0.22, 0.3, 0.46) * pow(d, 10.0) * 0.3;
          gl_FragColor = vec4(c, 1.0);
        }
      `,
    })
    const sky = new THREE.Mesh(new THREE.SphereGeometry(620, 32, 18), mat)
    sky.frustumCulled = false
    this.scene.add(sky)

    const count = 1400
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(0.06 + Math.random() * 0.92)
      const r = 540
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.cos(phi)
      positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const stars = new THREE.Points(
      geo,
      new THREE.PointsMaterial({
        size: 2.1,
        color: 0xdfe8ff,
        transparent: true,
        opacity: 0.92,
        depthWrite: false,
      }),
    )
    stars.frustumCulled = false
    this.scene.add(stars)

    // A tight blue-white star cluster, like the one over the reference tower.
    const clusterCount = 1500
    const cluster = new Float32Array(clusterCount * 3)
    const center = new THREE.Vector3(0.34, 0.62, -0.72).normalize()
    for (let i = 0; i < clusterCount; i++) {
      const spread = 0.11 + Math.random() ** 2.2 * 0.24
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(1 - Math.random() * 0.7)
      const dir = center
        .clone()
        .add(
          new THREE.Vector3(
            Math.sin(phi) * Math.cos(theta),
            Math.sin(phi) * Math.sin(theta),
            Math.cos(phi),
          ).multiplyScalar(spread),
        )
        .normalize()
        .multiplyScalar(535)
      cluster[i * 3] = dir.x
      cluster[i * 3 + 1] = dir.y
      cluster[i * 3 + 2] = dir.z
    }
    const clusterGeo = new THREE.BufferGeometry()
    clusterGeo.setAttribute('position', new THREE.BufferAttribute(cluster, 3))
    const clusterStars = new THREE.Points(
      clusterGeo,
      new THREE.PointsMaterial({
        size: 1.8,
        color: 0xbcd8ff,
        transparent: true,
        opacity: 0.9,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    clusterStars.frustumCulled = false
    this.scene.add(clusterStars)

    // A crisp moon disc plus a soft halo, aligned with the sky shader's moon
    // direction so the water and roof tiles reflect the same source.
    const moonDir = new THREE.Vector3(-0.42, 0.52, 0.42).normalize()
    const moon = new THREE.Mesh(
      new THREE.SphereGeometry(5.2, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xf3f7ff }),
    )
    moon.position.copy(moonDir).multiplyScalar(520)
    this.scene.add(moon)
    const halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this.glow,
        color: 0xbcd4ff,
        transparent: true,
        opacity: 0.5,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    halo.position.copy(moon.position)
    halo.scale.setScalar(48)
    this.scene.add(halo)
  }

  /** Drifting wish lanterns: warm bokeh above the roofline, the scene's signature. */
  private addSkyLanterns() {
    // A dense drift of wish lanterns is the reference's signature; keep them
    // small and high so they read as depth instead of near-camera blobs.
    const count = 220
    const positions = new Float32Array(count * 3)
    const sizes = new Float32Array(count)
    const colors = new Float32Array(count * 3)
    const speeds = new Float32Array(count)
    const phases = new Float32Array(count)
    const drifts = new Float32Array(count)
    const warm = new THREE.Color('#ffd9a0')
    const amber = new THREE.Color('#ffb877')
    for (let i = 0; i < count; i++) {
      positions[i * 3] = -45 + Math.random() * 90
      positions[i * 3 + 1] = 14 + Math.random() * 56
      positions[i * 3 + 2] = -160 + Math.random() * 360
      sizes[i] = 0.28 + Math.random() * 0.48
      const c = i % 6 === 0 ? amber : warm
      colors[i * 3] = c.r
      colors[i * 3 + 1] = c.g
      colors[i * 3 + 2] = c.b
      speeds[i] = 0.3 + Math.random() * 0.45
      phases[i] = Math.random() * Math.PI * 2
      drifts[i] = 0.08 + Math.random() * 0.22
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1))
    geo.setAttribute('aColor', new THREE.BufferAttribute(colors, 3))
    const mat = new THREE.ShaderMaterial({
      uniforms: { uMap: { value: this.skyGlow }, uScale: { value: window.innerHeight * 0.5 } },
      vertexShader: /* glsl */ `
        attribute float aSize;
        attribute vec3 aColor;
        uniform float uScale;
        varying vec3 vColor;
        void main() {
          vColor = aColor;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = aSize * uScale / max(1.0, -mv.z);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform sampler2D uMap;
        varying vec3 vColor;
        void main() {
          vec4 t = texture2D(uMap, gl_PointCoord);
          gl_FragColor = vec4(vColor * t.rgb, t.a * 0.92);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const points = new THREE.Points(geo, mat)
    points.frustumCulled = false
    this.scene.add(points)
    this.skyLanterns = { points, positions, speeds, phases, drifts }
  }

  private addLights() {
    // Mirrors the lookdev rig: a low blue world, a weak moon key, and a regular
    // rhythm of warm practicals.  The paper windows carry their own emission;
    // these lights give the plaster, timber and stone something to model.
    this.scene.add(new THREE.AmbientLight(0x1a2a4f, 0.1))
    this.scene.add(new THREE.HemisphereLight(0x2e4c82, 0x04060c, 0.32))

    // Each wash stands on the river side of the bank it lights, so the shop
    // fronts receive it instead of being backlit from behind.
    for (const [fromX, toX] of [
      [-70, 20],
      [70, -20],
    ] as const) {
      const wash = new THREE.DirectionalLight(0xffb877, 0.42)
      wash.position.set(fromX, 36, -10)
      wash.target.position.set(toX, 2.5, -10)
      this.scene.add(wash)
      this.scene.add(wash.target)
    }

    const moon = new THREE.DirectionalLight(0x9fc0ff, 0.55)
    moon.position.set(-90, 130, 70)
    moon.target.position.set(0, 0, -20)
    moon.castShadow = true
    // The shadow map is frozen after the world loads, so the higher resolution
    // costs nothing per frame and doubles the shadow detail across the street.
    const shadowSize = this.highTier ? 4096 : 2048
    moon.shadow.mapSize.set(shadowSize, shadowSize)
    moon.shadow.camera.left = -140
    moon.shadow.camera.right = 140
    moon.shadow.camera.top = 140
    moon.shadow.camera.bottom = -140
    moon.shadow.camera.near = 20
    moon.shadow.camera.far = 460
    moon.shadow.bias = -0.0004
    moon.shadow.normalBias = 0.6
    this.scene.add(moon)
    this.scene.add(moon.target)

    const fill = new THREE.DirectionalLight(0x4d6ba8, 0.16)
    fill.position.set(130, 70, -110)
    fill.target.position.set(0, 0, 20)
    this.scene.add(fill)
    this.scene.add(fill.target)

    const warm = (x: number, y: number, z: number, intensity: number, range: number) => {
      const light = new THREE.PointLight(0xffae63, intensity, range, 2)
      light.position.set(x, y, z)
      this.scene.add(light)
    }
    // Blender's street lamps stand on the promenade at 4.6 m, not inside the
    // shop volumes; keep that spacing so the facades get alternating warm bays.
    for (const y of [-115, -78, -40, 0, 38, 78, 118, 158]) {
      warm(15.2, 4.6, -y, 52, 24)
      warm(-15.2, 4.6, -y, 46, 24)
    }
    for (const x of [-14, -5, 5, 14]) warm(x, 7, -10, 32, 11)
    // Gate, performance stage, ferry docks and plaza get their own practicals.
    warm(16.0, 4.6, 120, 40, 12)
    warm(-14.2, 3.2, -26, 60, 12)
    warm(15.0, 3.2, 48, 34, 9)
    warm(-15.0, 3.2, 90, 34, 9)
    for (const [y, intensity] of [
      [6, 120],
      [12, 96],
      [18, 86],
      [24, 78],
      [30, 70],
    ] as const) {
      warm(0, y, -78, intensity, 18)
    }
    warm(31, 6, -62, 62, 14)
  }

  private bindEvents() {
    this.canvas.addEventListener('pointerdown', this.onPointerDown)
    this.canvas.addEventListener('pointermove', this.onPointerMove)
    window.addEventListener('pointerup', this.onPointerUp)
    window.addEventListener('keydown', this.onKeyDown)
    window.addEventListener('keyup', this.onKeyUp)
    window.addEventListener('resize', this.resize)
    document.addEventListener('pointerlockchange', this.onLockChange)
  }

  private onLockChange = () => {
    this.pointerLocked = document.pointerLockElement === this.canvas
  }

  private onPointerDown = (e: PointerEvent) => {
    this.audio.unlock()
    if (e.pointerType === 'mouse' && !this.pointerLocked) {
      void this.canvas.requestPointerLock?.()
      return
    }
    this.dragging = true
    this.lastPointer = { x: e.clientX, y: e.clientY }
  }

  private onPointerMove = (e: PointerEvent) => {
    if (this.pointerLocked) {
      this.look(e.movementX * 0.0022, e.movementY * 0.0022)
      return
    }
    if (!this.dragging) return
    this.look((e.clientX - this.lastPointer.x) * 0.004, (e.clientY - this.lastPointer.y) * 0.004)
    this.lastPointer = { x: e.clientX, y: e.clientY }
  }

  private onPointerUp = () => {
    this.dragging = false
  }

  private look(dx: number, dy: number) {
    this.pan = null
    this.viewTween = null
    this.yaw += dx
    this.pitch = Math.max(-1.15, Math.min(1.05, this.pitch - dy))
  }

  private onKeyDown = (e: KeyboardEvent) => {
    if (e.code === 'KeyE') {
      this.interact()
      return
    }
    if (e.code === 'KeyC') {
      this.toggleCollisionDebug()
      return
    }
    if (e.code === 'Escape') {
      this.closePanel()
      return
    }
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ShiftLeft', 'ShiftRight'].includes(e.code)) {
      e.preventDefault()
      this.viewTween = null
    }
    this.keys.add(e.code)
  }

  private onKeyUp = (e: KeyboardEvent) => {
    this.keys.delete(e.code)
  }

  private resize = () => {
    const w = this.canvas.clientWidth || window.innerWidth
    const h = this.canvas.clientHeight || window.innerHeight
    this.renderer.setSize(w, h, false)
    this.composer.setSize(w, h)
    this.camera.aspect = w / Math.max(1, h)
    this.camera.updateProjectionMatrix()
    if (this.reflectionTarget) {
      const buffer = this.renderer.getDrawingBufferSize(new THREE.Vector2())
      // Slightly under half resolution keeps the mirror soft like water and
      // leaves most of the frame budget to the main pass.
      this.reflectionTarget.setSize(
        Math.max(1, Math.round(buffer.x * 0.35)),
        Math.max(1, Math.round(buffer.y * 0.35)),
      )
    }
    const skyMat = this.skyLanterns?.points.material as THREE.ShaderMaterial | undefined
    if (skyMat) skyMat.uniforms.uScale.value = (h * this.renderer.getPixelRatio()) / 2
  }

  // ---------------------------------------------------------------- loading

  async load() {
    const total = 9
    let done = 0
    const tick = () => {
      done++
      this.cb.onProgress(done, total)
    }

    // The same Blender export owns the visuals and the collision.  Loading the
    // layout before the player moves means a stale hand-written rectangle can
    // never block visibly open paving.
    const layoutJob = fetch(`${MODEL_BASE}layout.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`layout.json ${response.status}`)
        return response.json() as Promise<CollisionLayout>
      })
      .then((layout) => {
        this.layout = layout
        this.groundField = new WalkableGround(layout)
        this.obstacleField = new ObstacleField(layout.obstacles)
        this.playerGround = layout.groundZ
        this.riverHalf = layout.riverHalf
        this.waterMat.uniforms.uBankX.value = layout.riverHalf
        // The reeds read the bank line from the same layout, so a wider canal
        // moves the planting with the water instead of leaving it on dry stone.
        this.flora = new WaterlineFlora(layout.riverHalf, 0.05)
        this.scene.add(this.flora.object)
        this.player.set(layout.spawn.x, layout.groundZ + EYE, -layout.spawn.y)
        this.camera.position.copy(this.player)
        this.buildCollisionDebug()
        tick()
      })

    const worldJob = this.loader.loadAsync(`${MODEL_BASE}world.glb`).then((gltf) => {
      const world = gltf.scene
      world.name = 'LanternRiver_World'
      const maxAnisotropy = this.renderer.capabilities.getMaxAnisotropy()
      world.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        // One merged mesh spans the whole street; frustum culling would always
        // pass, so skip it and keep the 39 material primitives together.
        mesh.frustumCulled = false
        mesh.castShadow = true
        mesh.receiveShadow = true
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const m of mats) {
          if (!m) continue
          const std = m as THREE.MeshPhysicalMaterial
          // The GLB ships the full material graph, including the baked maps;
          // keep emissive strength and every physical lobe untouched.  Only
          // texture sampling needs the runtime renderer's anisotropy limit.
          for (const key of ['map', 'normalMap', 'roughnessMap'] as const) {
            const texture = std[key]
            if (texture) {
              texture.anisotropy = maxAnisotropy
              texture.needsUpdate = true
            }
          }
          std.envMapIntensity = 0.8
          std.dithering = true
        }
      })
      this.tuneGlowMaterials(world)
      this.scene.add(world)
      this.prepareTower(world)
      tick()
    })

    const templates = [
      'model-river-lantern-lotus',
      'model-river-lantern-paperboat',
      'model-river-lantern-fish',
    ]
    const templateJobs = templates.map(async (id) => {
      const gltf = await this.loader.loadAsync(`${TEMPLATE_BASE}${id}.glb`)
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const m of mats) {
          const std = m as THREE.MeshStandardMaterial
          if (std.name === 'SY_Lantern') std.emissiveIntensity = 2.2
          if (std.name === 'SY_Paper') std.emissiveIntensity = 1.6
        }
      })
      this.lanternTemplates.set(id, gltf.scene)
      tick()
    })

    await Promise.all([layoutJob, worldJob, ...templateJobs])
    this.addGroundGlow()
    this.seedAmbientLanterns()
    this.pushHud()
    this.worldReady = true
    this.cb.onReady()
    this.loop()
  }

  /**
   * The Blender build carries emissive strengths tuned for Cycles.  In the web
   * renderer the string bulbs fall below the bloom threshold and read as flat
   * discs.  The reference leans on hot lantern cores and pink canopies, so lift
   * the few named materials that carry that read.
   */
  private tuneGlowMaterials(world: THREE.Object3D) {
    const glowStrength: Record<string, number> = {
      // Above ~3 the paper clips to a white disc at arm's length; the lantern
      // frame and the warm paper tone only survive below that.
      MAT_SCENE_BulbWarm: 2.7,
      MAT_SCENE_BulbRed: 3.2,
      MAT_SCENE_BulbGold: 2.4,
      MAT_SCENE_QuayLantern: 2.6,
      MAT_SCENE_BoatPaper: 3.4,
      // Shoji paper carries the shopfronts; at 1.0 they sit flat under the
      // night grade, and the reference reads as walls of warm window light.
      SY_Paper: 1.35,
      SY_Lantern: 1.8,
      MAT_Lantern_Paper: 1.6,
      MAT_Pavilion_Lantern: 1.7,
      // Foliage cards carry their colour in the atlas, so only the emission is
      // lifted here; tinting the base map would turn the blossoms into a
      // single flat pink.
      MAT_SCENE_BlossomCard: 0.38,
      MAT_SCENE_WillowCard: 0.3,
    }
    // The atlases are painted for neutral daylight.  Under the warm night grade
    // a pale blossom map turns peach, so pull both the albedo and the glow
    // towards rose.
    const cardTint: Record<string, [number, number]> = {
      MAT_SCENE_BlossomCard: [0xffb4cc, 0xf07fa0],
      MAT_SCENE_WillowCard: [0xffffff, 0x9fc47a],
    }
    world.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      for (const m of mats) {
        const std = m as THREE.MeshStandardMaterial
        if (!std?.name) continue
        const strength = glowStrength[std.name]
        if (strength === undefined) continue
        std.emissiveIntensity = strength
        const tint = cardTint[std.name]
        if (tint) {
          std.color.setHex(tint[0])
          std.emissive.setHex(tint[1])
        }
        std.needsUpdate = true
      }
    })
  }

  /**
   * Render the world from the camera mirrored across the water plane into a
   * half-resolution target.  The water shader samples it in screen space, so
   * the facades and lanterns reflect without a second copy of the world in the
   * main pass.  An oblique projection clips everything below the surface.
   */
  private renderReflection() {
    const target = this.reflectionTarget
    if (!target || !this.worldReady) return
    // The canal is calm and the camera moves slowly; a 30 Hz mirror is
    // indistinguishable from a per-frame one and leaves the main pass budget.
    if (this.reflectionTick++ % 2 !== 0) return

    const camera = this.camera
    const waterY = 0.05
    const normal = new THREE.Vector3(0, 1, 0)
    const reflector = new THREE.Vector3(0, waterY, 0)

    // Reflect the camera position and look-at point across the surface.
    const view = new THREE.Vector3().subVectors(reflector, camera.position)
    view.reflect(normal).negate().add(reflector)
    const lookAt = new THREE.Vector3(0, 0, -1).applyMatrix4(camera.matrixWorld)
    const targetPoint = new THREE.Vector3().subVectors(reflector, lookAt)
    targetPoint.reflect(normal).negate().add(reflector)

    const virtual = this.reflectionCamera
    virtual.position.copy(view)
    virtual.up.set(0, 1, 0).applyQuaternion(camera.quaternion).reflect(normal)
    virtual.lookAt(targetPoint)
    virtual.near = camera.near
    virtual.far = camera.far
    virtual.updateMatrixWorld()
    virtual.projectionMatrix.copy(camera.projectionMatrix)
    virtual.projectionMatrixInverse.copy(virtual.projectionMatrix).invert()

    // Oblique near plane (Lengyel) clips the world at the waterline.
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, reflector)
    plane.applyMatrix4(virtual.matrixWorldInverse)
    const clip = new THREE.Vector4(plane.normal.x, plane.normal.y, plane.normal.z, plane.constant)
    const q = new THREE.Vector4()
    const pm = virtual.projectionMatrix
    q.x = (Math.sign(clip.x) + pm.elements[8]) / pm.elements[0]
    q.y = (Math.sign(clip.y) + pm.elements[9]) / pm.elements[5]
    q.z = -1
    q.w = (1 + pm.elements[10]) / pm.elements[14]
    clip.multiplyScalar(2 / clip.dot(q))
    pm.elements[2] = clip.x
    pm.elements[6] = clip.y
    pm.elements[10] = clip.z + 1 - 0.003
    pm.elements[14] = clip.w
    virtual.projectionMatrixInverse.copy(pm).invert()

    // Project water-surface points into the reflection target.  The oblique
    // projection differs from the main camera's, so this matrix is the only
    // mapping that stays aligned at grazing angles.
    const textureMatrix = new THREE.Matrix4().set(
      0.5,
      0,
      0,
      0.5,
      0,
      0.5,
      0,
      0.5,
      0,
      0,
      0.5,
      0.5,
      0,
      0,
      0,
      1,
    )
    textureMatrix.multiply(virtual.projectionMatrix)
    textureMatrix.multiply(virtual.matrixWorldInverse)
    this.waterMat.uniforms.uReflectionMatrix.value.copy(textureMatrix)

    const previous = this.renderer.getRenderTarget()
    this.water.visible = false
    this.renderer.setRenderTarget(target)
    this.renderer.clear()
    this.renderer.render(this.scene, virtual)
    this.renderer.setRenderTarget(previous)
    this.water.visible = true
    this.waterMat.uniforms.uReflectionStrength.value = 1
  }

  /**
   * Draws the exported layout: cyan walkable triangles, orange obstacle
   * footprints.  This is the visual proof that collision and art share one
   * source, and the tool for finding a gap the exporter missed.
   */
  private buildCollisionDebug() {
    const layout = this.layout
    if (!layout) return
    const group = new THREE.Group()
    group.name = 'CollisionDebug'
    group.visible = false

    const lift = 0.045
    const walk: number[] = []
    const tris = layout.walkable
    for (let i = 0; i < tris.length; i += 9) {
      const ax = tris[i]
      const ay = tris[i + 1]
      const az = tris[i + 2]
      const bx = tris[i + 3]
      const by = tris[i + 4]
      const bz = tris[i + 5]
      const cx = tris[i + 6]
      const cy = tris[i + 7]
      const cz = tris[i + 8]
      walk.push(ax, az + lift, -ay, bx, bz + lift, -by)
      walk.push(bx, bz + lift, -by, cx, cz + lift, -cy)
      walk.push(cx, cz + lift, -cy, ax, az + lift, -ay)
    }
    const walkGeo = new THREE.BufferGeometry()
    walkGeo.setAttribute('position', new THREE.Float32BufferAttribute(walk, 3))
    group.add(
      new THREE.LineSegments(
        walkGeo,
        new THREE.LineBasicMaterial({
          color: 0x4fe3ff,
          transparent: true,
          opacity: 0.5,
          depthTest: false,
        }),
      ),
    )

    const block: number[] = []
    for (const obstacle of layout.obstacles) {
      const cos = Math.cos(obstacle.rot)
      const sin = Math.sin(obstacle.rot)
      const corners: [number, number, number][] = []
      for (const [sx, sy] of [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ] as const) {
        const lx = sx * obstacle.hx
        const ly = sy * obstacle.hy
        const wx = obstacle.x + lx * cos - ly * sin
        const wy = obstacle.y + lx * sin + ly * cos
        corners.push([wx, wy, 0])
      }
      const base = SCENE.groundZ + 0.06
      const top = Math.max(base + 0.2, obstacle.top)
      for (let i = 0; i < 4; i++) {
        const a = corners[i]
        const b = corners[(i + 1) % 4]
        block.push(a[0], base, -a[1], b[0], base, -b[1])
        block.push(a[0], top, -a[1], b[0], top, -b[1])
        block.push(a[0], base, -a[1], a[0], top, -a[1])
      }
    }
    const blockGeo = new THREE.BufferGeometry()
    blockGeo.setAttribute('position', new THREE.Float32BufferAttribute(block, 3))
    group.add(
      new THREE.LineSegments(
        blockGeo,
        new THREE.LineBasicMaterial({
          color: 0xff8a4c,
          transparent: true,
          opacity: 0.65,
          depthTest: false,
        }),
      ),
    )
    group.traverse((o) => {
      o.renderOrder = 999
    })
    this.scene.add(group)
    this.collisionDebug = group
  }

  private toggleCollisionDebug() {
    if (!this.collisionDebug) return
    this.collisionDebug.visible = !this.collisionDebug.visible
    this.cb.onToast(
      this.collisionDebug.visible ? '碰撞可见：青色可行走 · 橙色阻挡' : '碰撞线框已关闭',
    )
  }

  private prepareTower(_root: THREE.Object3D) {
    for (const y of [5, 10, 16, 22, 28]) {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: this.glow,
          color: 0xffc98a,
          transparent: true,
          opacity: 0.14,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      )
      sprite.position.set(0, y, -78)
      sprite.scale.setScalar(8)
      this.towerGlow.push(sprite)
      this.scene.add(sprite)
    }
  }

  /** Warm pools on the paving: cheap, and they do most of the "lit street" work. */
  private addGroundGlow() {
    const geo = new THREE.PlaneGeometry(1, 1)
    const mat = new THREE.MeshBasicMaterial({
      map: this.glow,
      color: 0xffb877,
      transparent: true,
      opacity: 0.2,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const pools: [number, number, number, number][] = []
    for (let y = -126; y <= 162; y += 16) {
      pools.push([16.4, y, 7, 0.16])
      pools.push([-16.4, y + 8, 7, 0.1])
    }
    pools.push([0, 10, 12, 0.28])
    pools.push([0, 78, 16, 0.22])
    for (const [x, y, size, opacity] of pools) {
      const mesh = new THREE.Mesh(geo, mat.clone())
      ;(mesh.material as THREE.MeshBasicMaterial).opacity = opacity
      mesh.rotation.x = -Math.PI / 2
      mesh.position.set(x, SCENE.groundZ + 0.03, -y)
      mesh.scale.set(size, size, 1)
      this.scene.add(mesh)
    }
  }

  private seedAmbientLanterns() {
    for (let i = 0; i < 26; i++) {
      const style = i % 4 === 0 ? 'model-river-lantern-paperboat' : 'model-river-lantern-lotus'
      const lane = ((i * 7) % 17) - 8
      this.spawnLantern(style, lane, -128 + i * 11.6, 0.32 + (i % 4) * 0.08)
    }
  }

  private spawnLantern(style: string, x: number, z: number, speed: number, ripple = false) {
    const template = this.lanternTemplates.get(style)
    if (!template) return
    const obj = template.clone(true)
    obj.position.set(x, 0.08, z)
    obj.scale.setScalar(0.9 + Math.random() * 0.35)
    this.scene.add(obj)
    const halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this.glow,
        color: 0xffc477,
        transparent: true,
        opacity: 0.3,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    halo.position.set(x, 0.45, z)
    halo.scale.setScalar(1.05)
    this.scene.add(halo)
    this.lanterns.push({ obj, halo, t: Math.random() * 10, speed, lane: z })
    if (ripple) this.effects.push(new Ripple(this.scene, new THREE.Vector3(x, 0, z)))
    if (this.lanterns.length > 70) {
      const old = this.lanterns.shift()
      if (old) {
        this.scene.remove(old.obj)
        this.scene.remove(old.halo)
        old.halo.material.dispose()
      }
    }
  }

  // ---------------------------------------------------------------- interaction

  interact() {
    if (this.panel) return
    const id = this.nearby
    if (!id) return
    this.audio.unlock()
    switch (id) {
      case 'entrance':
        if (this.phase !== 'idle') {
          this.cb.onToast('花灯已经在你手里了')
          return
        }
        this.openPanel({
          title: '灯门',
          body: '守灯人递来一盏素纸花灯。「提着它，去街市里换一枚灯芯。」',
          options: [{ label: '提起花灯' }],
        })
        return
      case 'riddle':
        if (this.phase === 'idle') {
          this.cb.onToast('先去牌坊领一盏花灯')
          return
        }
        if (this.riddlesSolved >= RIDDLES.length) {
          this.cb.onToast('三枚灯谜都答对了，灯芯已经够了')
          return
        }
        this.openRiddle()
        return
      case 'tower':
        if (this.phase === 'idle') {
          this.cb.onToast('先去牌坊领一盏花灯')
          return
        }
        this.openStyles()
        return
      case 'quay':
        if (!this.style) {
          this.cb.onToast('先去灯楼挑一盏河灯')
          return
        }
        this.openBlessings()
        return
      case 'performance':
        this.openShow()
        return
    }
  }

  private openPanel(panel: Panel) {
    this.panel = panel
    this.cb.onPanel(panel)
  }

  private openRiddle() {
    const r = RIDDLES[this.riddleIndex]
    this.openPanel({
      title: `灯谜 ${this.riddleIndex + 1} / ${RIDDLES.length}`,
      body: r.question,
      options: r.options.map((label) => ({ label })),
    })
  }

  private openStyles() {
    this.openPanel({
      title: '上元灯楼 · 挑一盏河灯',
      body: `灯芯 ${this.wicks} 枚。灯芯越多，能挑的灯越精巧。`,
      options: LANTERN_STYLES.map((s) => ({
        label: s.name,
        note: s.cost === 0 ? s.note : `${s.note} · 需 ${s.cost} 枚灯芯`,
        disabled: this.wicks < s.cost,
      })),
    })
  }

  private openBlessings() {
    this.openPanel({
      title: '埠头 · 写一句祝词',
      body: `你手里的${this.style}已经点好了。选一句祝词，把它放进水里。`,
      options: BLESSINGS.map((label) => ({ label })),
    })
  }

  private openShow() {
    this.openPanel({
      title: '河对岸 · 花台',
      body: '铁水已经烧到发白。要不要现在就看一场打铁花？',
      options: [{ label: '看一场' }],
    })
  }

  choose(index: number) {
    const panel = this.panel
    if (!panel) return
    const option = panel.options[index]
    if (!option || option.disabled) return

    if (panel.title === '灯门') {
      this.phase = 'claimed'
      this.cb.onToast('花灯亮了。去街市里猜灯谜，换一枚灯芯。')
      this.audio.chime(660)
      this.closePanel()
      this.pushHud()
      return
    }

    if (panel.title.startsWith('灯谜')) {
      const riddle = RIDDLES[this.riddleIndex]
      if (index === riddle.answer) {
        this.wicks++
        this.riddlesSolved++
        this.riddleIndex++
        this.audio.chime(880)
        this.cb.onToast(`答对了 · 灯芯 +1（${this.wicks} 枚）`)
        this.closePanel()
        this.pushHud()
      } else {
        this.panel = { ...panel, hint: riddle.hint }
        this.cb.onPanel(this.panel)
        this.audio.thud()
      }
      return
    }

    if (panel.title.includes('挑一盏河灯')) {
      const style = LANTERN_STYLES[index]
      if (this.wicks < style.cost) return
      this.wicks -= style.cost
      this.style = style.name
      this.phase = 'style'
      this.audio.chime(1040)
      this.cb.onToast(`拿到了${style.name}。去埠头把它放进河里。`)
      this.closePanel()
      this.pushHud()
      return
    }

    if (panel.title.includes('写一句祝词')) {
      this.blessing = BLESSINGS[index]
      this.releaseLantern()
      this.closePanel()
      return
    }

    if (panel.title.includes('花台')) {
      this.closePanel()
      this.startShow()
    }
  }

  private releaseLantern() {
    const style = LANTERN_STYLES.find((s) => s.name === this.style)
    const id = style?.file ?? 'model-river-lantern-lotus'
    this.spawnLantern(
      id,
      this.riverHalf - 1.4 - Math.random() * 1.2,
      -118,
      0.42 + Math.random() * 0.16,
      true,
    )
    this.released++
    this.phase = 'released'
    this.audio.splash()
    this.cb.onToast(`河灯落水了 ·「${this.blessing}」`)
    this.pushHud()
    if (this.autoShow < 0 && this.showClock < 0) this.autoShow = 4.5
  }

  private startShow() {
    this.phase = 'show'
    this.showClock = 0
    this.showStage = 0
    this.autoShow = -1
    this.pushHud()
    this.cb.onToast('灯楼要亮了')
  }

  closePanel() {
    if (!this.panel) return
    this.panel = null
    this.cb.onPanel(null)
  }

  private pushHud() {
    this.cb.onHud({
      phase: this.phase,
      wicks: this.wicks,
      riddles: this.riddlesSolved,
      released: this.released,
      style: this.style,
      blessing: this.blessing,
      showActive: this.showStage > 0 && this.showStage < 5,
    })
  }

  setViewpoint(index: number) {
    const v = VIEWPOINTS[index]
    if (!v) return
    const dx = v.look[0] - v.pos[0]
    const dz = -(v.look[1] - v.pos[1])
    const dy = v.look[2] - v.pos[2]
    const targetYaw = Math.atan2(dz, dx)
    let turn = targetYaw - this.yaw
    while (turn > Math.PI) turn -= Math.PI * 2
    while (turn < -Math.PI) turn += Math.PI * 2
    this.viewTween = {
      from: this.player.clone(),
      to: new THREE.Vector3(v.pos[0], v.pos[2], -v.pos[1]),
      fromYaw: this.yaw,
      toYaw: this.yaw + turn,
      fromPitch: this.pitch,
      toPitch: Math.atan2(dy, Math.hypot(dx, dz)),
      t: 0,
    }
    this.pan = null
    this.cb.onToast(`机位：${v.name}`)
  }

  /** Renderer counters, for the preview capture script. */
  stats() {
    const info = this.renderer.info
    return {
      drawCalls: info.render.calls,
      triangles: info.render.triangles,
      geometries: info.memory.geometries,
      textures: info.memory.textures,
      lanterns: this.lanterns.length,
      obstacles: this.obstacleField ? this.layout?.obstacles.length : 0,
      ground: +this.playerGround.toFixed(2),
      reflection: Boolean(this.reflectionTarget),
      phase: this.phase,
      showStage: this.showStage,
    }
  }

  /** Debug helper: first meshes under a screen point (NDC). */
  pick(nx = 0, ny = 0) {
    const ray = new THREE.Raycaster()
    ray.setFromCamera(new THREE.Vector2(nx, ny), this.camera)
    const meshes: THREE.Object3D[] = []
    this.scene.traverse((o) => {
      if ((o as THREE.Mesh).isMesh) meshes.push(o)
    })
    return ray
      .intersectObjects(meshes, false)
      .slice(0, 3)
      .map((h) => ({ name: h.object.name, d: +h.distance.toFixed(1) }))
  }

  /** Debug helper: current position in Blender coordinates. */
  where() {
    return {
      x: +this.player.x.toFixed(1),
      y: +(-this.player.z).toFixed(1),
      z: +this.player.y.toFixed(2),
    }
  }

  /** Debug helper: face a Blender (x, y) point from the current spot. */
  lookAt(x: number, y: number, height = 1.6) {
    const dx = x - this.player.x
    const dz = -y - this.player.z
    const dy = height - this.player.y
    this.yaw = Math.atan2(dz, dx)
    this.pitch = Math.atan2(dy, Math.hypot(dx, dz))
  }

  /** Debug/preview helper: move to a Blender (x, y) spot at walking height. */
  teleport(x: number, y: number) {
    // A running viewpoint tween would pull the player back to its destination.
    this.viewTween = null
    this.pan = null
    // Debug moves are allowed onto any walkable surface (bridge deck included),
    // so sample without a rise limit instead of snapping to the nearest quay.
    const ground = this.groundField?.heightAt(x, y, Number.POSITIVE_INFINITY) ?? SCENE.groundZ
    this.playerGround = ground
    this.player.set(x, ground + EYE, -y)
    this.camera.position.copy(this.player)
  }

  togglePhoto(): boolean {
    this.photo = !this.photo
    return this.photo
  }

  setTouch(move: number, strafe: number) {
    this.touchMove = move
    this.touchStrafe = strafe
  }

  setMuted(muted: boolean) {
    this.audio.setMuted(muted)
  }

  // ---------------------------------------------------------------- loop

  private loop = () => {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    const raw = this.clock.getDelta()
    // Movement stays stable under hitches, but event timing must follow the wall clock,
    // otherwise the show crawls whenever the frame rate dips.
    this.update(Math.min(raw, 0.05), Math.min(raw, 0.3))
    this.camera.updateMatrixWorld()
    this.renderReflection()
    this.renderer.info.reset()
    this.composer.render()

    // The moon is the only shadow caster and the level never moves, so the
    // shadow map only has to be drawn once the world is in place.  Freezing it
    // removes the whole million-triangle depth pass from every later frame.
    if (this.worldReady && !this.shadowFrozen) {
      this.shadowFrames += 1
      if (this.shadowFrames > 2) {
        this.renderer.shadowMap.autoUpdate = false
        this.shadowFrozen = true
      }
    }
  }

  private update(dt: number, eventDt = dt) {
    if (this.viewTween) {
      this.updateViewTween(dt)
    } else {
      this.move(dt)
      this.updatePan(dt)
      // Steps and the bridge ramp change the ground height under the feet; ease
      // the eye to it so crossings read as a walk instead of a lift.
      this.player.y += (this.playerGround + EYE - this.player.y) * Math.min(1, dt * 12)
    }
    this.camera.position.copy(this.player)
    const dir = new THREE.Vector3(
      Math.cos(this.pitch) * Math.cos(this.yaw),
      Math.sin(this.pitch),
      Math.cos(this.pitch) * Math.sin(this.yaw),
    )
    this.camera.lookAt(this.player.clone().add(dir))

    this.waterMat.uniforms.uTime.value += dt
    this.atmosphere.update(dt)
    this.flora?.update(dt)
    this.grading.uniforms.uTime.value += dt

    for (const wheel of this.wheelPivots) wheel.rotation.z += dt * 0.24

    this.updateLanterns(dt)
    this.updateSkyLanterns(dt)
    this.updateShow(eventDt)
    this.updateAmbientFireworks(dt)
    this.updateEffects(dt)
    this.updateNearby()
  }

  /** A gentle, interruptible turn toward a moment worth watching (the show). */
  private panTo(target: THREE.Vector3, seconds: number) {
    if (this.idleClock < 1.2) return
    const dx = target.x - this.player.x
    const dz = target.z - this.player.z
    const dy = target.y - this.player.y
    this.pan = {
      yaw: Math.atan2(dz, dx),
      pitch: Math.max(-0.25, Math.min(0.32, Math.atan2(dy, Math.hypot(dx, dz)))),
      t: seconds,
    }
  }

  private updatePan(dt: number) {
    if (!this.pan) return
    this.pan.t -= dt
    const k = Math.min(1, dt * 2.2)
    let d = this.pan.yaw - this.yaw
    while (d > Math.PI) d -= Math.PI * 2
    while (d < -Math.PI) d += Math.PI * 2
    this.yaw += d * k
    this.pitch += (this.pan.pitch - this.pitch) * k
    if (this.pan.t <= 0) this.pan = null
  }

  /** Smooth, interruptible move between the authored viewpoints. */
  private updateViewTween(dt: number) {
    const tween = this.viewTween
    if (!tween) return
    tween.t = Math.min(1.6, tween.t + dt)
    const raw = tween.t / 1.6
    const e = raw * raw * (3 - 2 * raw)
    this.player.lerpVectors(tween.from, tween.to, e)
    this.yaw = tween.fromYaw + (tween.toYaw - tween.fromYaw) * e
    this.pitch = tween.fromPitch + (tween.toPitch - tween.fromPitch) * e
    if (raw >= 1) {
      this.viewTween = null
      const ground = this.groundField?.heightAt(
        this.player.x,
        -this.player.z,
        Number.POSITIVE_INFINITY,
      )
      if (ground !== undefined && ground !== null) this.playerGround = ground
    }
  }

  private move(dt: number) {
    if (this.panel) return
    let f = (this.keys.has('KeyW') ? 1 : 0) - (this.keys.has('KeyS') ? 1 : 0)
    let r = (this.keys.has('KeyD') ? 1 : 0) - (this.keys.has('KeyA') ? 1 : 0)
    if (this.touchMove || this.touchStrafe) {
      f = this.touchMove
      r = this.touchStrafe
    }
    if (!f && !r) {
      this.idleClock += dt
      return
    }
    // Walking takes the camera back: the show's auto-pan must never fight the player.
    this.idleClock = 0
    this.pan = null
    const speed = this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? RUN : SPEED
    const len = Math.hypot(f, r) || 1
    const fx = Math.cos(this.yaw)
    const fz = Math.sin(this.yaw)
    const rx = -Math.sin(this.yaw)
    const rz = Math.cos(this.yaw)
    const travel = speed * dt
    const dx = ((f * fx + r * rx) / len) * travel
    const dz = ((f * fz + r * rz) / len) * travel

    // Sub-step, then retry each axis alone.  Resolution pushes the circle out
    // of the obstacle, so the player slides along a shopfront or the bridge
    // parapet instead of sticking to it.
    const steps = Math.max(1, Math.ceil(travel / MAX_SUBSTEP))
    const sx = dx / steps
    const sz = dz / steps
    for (let i = 0; i < steps; i++) {
      if (this.tryStep(sx, sz)) continue
      const movedX = this.tryStep(sx, 0)
      const movedZ = this.tryStep(0, sz)
      if (!movedX && !movedZ) break
    }
  }

  /**
   * One sub-step against the exported collision.  The obstacle field resolves
   * the circle first; the ground field then decides whether the resolved spot
   * is actually walkable (quay, stair, plaza or bridge deck).  A spot with no
   * walkable triangle is water, a roof or the far bank, so the step dies there.
   */
  private tryStep(dx: number, dz: number): boolean {
    const nx = this.player.x + dx
    // Input deltas are game-space (y-up); the obstacle field speaks Blender y.
    const ny = -this.player.z - dz
    const resolved = this.obstacleField
      ? this.obstacleField.resolveCircle(nx, ny, PLAYER_RADIUS, this.playerGround)
      : { x: nx, y: ny, hit: false }
    const g = this.groundAt(resolved.x, resolved.y)
    if (g === null) return false
    const moved = Math.hypot(resolved.x - this.player.x, resolved.y + this.player.z)
    if (moved < 1e-4) return false
    this.player.x = resolved.x
    this.player.z = -resolved.y
    this.playerGround = g
    return true
  }

  private groundAt(x: number, y: number): number | null {
    return this.groundField?.heightAt(x, y, this.playerGround, STEP_UP, STEP_DOWN) ?? null
  }

  private updateLanterns(dt: number) {
    const xs = this.waterMat.uniforms.uLanternX.value as Float32Array
    const zs = this.waterMat.uniforms.uLanternZ.value as Float32Array
    const is = this.waterMat.uniforms.uLanternI.value as Float32Array
    xs.fill(0)
    zs.fill(0)
    is.fill(0)
    for (let i = 0; i < this.lanterns.length; i++) {
      const l = this.lanterns[i]
      l.t += dt
      l.obj.position.z += l.speed * dt
      l.obj.position.x = l.lane + Math.sin(l.t * 0.7) * 0.55
      l.obj.position.y = 0.08 + Math.sin(l.t * 1.6) * 0.03
      l.obj.rotation.y = Math.sin(l.t * 0.4) * 0.3
      l.halo.position.set(l.obj.position.x, 0.5, l.obj.position.z)
      if (i < 12) {
        xs[i] = l.obj.position.x
        zs[i] = l.obj.position.z
        is[i] = 0.8 + 0.2 * Math.sin(l.t * 2)
      }
      if (l.obj.position.z > 182) {
        l.obj.position.z = -140
        l.t = Math.random() * 6
      }
    }
  }

  private updateSkyLanterns(dt: number) {
    const s = this.skyLanterns
    if (!s) return
    const t = performance.now() * 0.001
    for (let i = 0; i < s.speeds.length; i++) {
      const p = i * 3
      s.positions[p + 1] += s.speeds[i] * dt
      s.positions[p] += s.drifts[i] * dt
      s.positions[p + 2] += Math.sin(t * 0.25 + s.phases[i]) * 0.06 * dt
      if (s.positions[p + 1] > 62) {
        s.positions[p + 1] = 12 + Math.random() * 5
        s.positions[p] = -26 + Math.random() * 52
        s.positions[p + 2] = -140 + Math.random() * 320
      }
    }
    s.points.geometry.attributes.position.needsUpdate = true
  }

  private updateShow(dt: number) {
    if (this.autoShow > 0) {
      this.autoShow -= dt
      if (this.autoShow <= 0) this.startShow()
    }
    if (this.showClock < 0) return
    this.showClock += dt
    const t = this.showClock

    if (t > 0.25 && this.showStage === 0) {
      this.showStage = 1
      this.audio.chime(520)
      // Frame the tower's middle, not its foot: from the quay the lantern
      // tower is 40 m away and its crown sits above a level camera.
      this.panTo(new THREE.Vector3(0, 11, -78), 1.8)
      for (let i = 0; i < 14; i++) {
        this.spawnLantern(
          i % 3 === 0 ? 'model-river-lantern-fish' : 'model-river-lantern-lotus',
          -this.riverHalf * 0.72 + (i % 5) * this.riverHalf * 0.36,
          -110 + i * 4.2,
          0.3 + (i % 3) * 0.12,
        )
      }
      this.pushHud()
    }
    if (t > 1.2 && this.showStage === 1) {
      this.showStage = 2
      this.audio.boom(0.85)
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(15, 3.6, -88)))
      this.pushHud()
    }
    if (t > 2.6 && this.showStage === 2) {
      this.showStage = 3
      this.effects.push(
        new ParticleBurst(this.scene, this.glow, new THREE.Vector3(12, 22, -80), {
          count: 460,
          color: 0xffc07a,
          spread: 1.5,
          speed: 7.5,
          size: 0.5,
          life: 2.2,
          gravity: 2,
          shell: true,
        }),
      )
      this.audio.boom(0.5)
      this.pushHud()
    }
    if (t > 5.0 && this.showStage === 3) {
      this.showStage = 4
      this.effects.push(
        new ParticleBurst(this.scene, this.glow, new THREE.Vector3(-10, 26, -78), {
          count: 460,
          color: 0xff8f60,
          spread: 1.5,
          speed: 7.5,
          size: 0.5,
          life: 2.2,
          gravity: 2,
          shell: true,
        }),
      )
      this.effects.push(
        new ParticleBurst(this.scene, this.glow, new THREE.Vector3(16, 20, -86), {
          count: 420,
          color: 0xffdfae,
          spread: 1.5,
          speed: 7,
          size: 0.46,
          life: 2.1,
          gravity: 2,
          shell: true,
        }),
      )
      this.audio.boom(0.7)
      this.pushHud()
    }
    if (t > 7.4 && this.showStage === 4) {
      this.showStage = 5
      this.cb.onToast('灯会到了最亮的时候')
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(-15, 3.6, -84)))
      this.pushHud()
    }
    if (t > 11.5 && this.showStage === 5) {
      this.showStage = 6
      this.effects.push(
        new ParticleBurst(this.scene, this.glow, new THREE.Vector3(-8, 28, -76), {
          count: 520,
          color: 0xffd8a8,
          spread: 1.5,
          speed: 8,
          size: 0.52,
          life: 2.3,
          gravity: 1.9,
          shell: true,
        }),
      )
      this.effects.push(
        new ParticleBurst(this.scene, this.glow, new THREE.Vector3(14, 24, -82), {
          count: 460,
          color: 0xff9a5a,
          spread: 1.5,
          speed: 7.5,
          size: 0.5,
          life: 2.2,
          gravity: 2,
          shell: true,
        }),
      )
      this.audio.boom(0.6)
      this.pushHud()
    }
    if (t > 16 && this.showStage === 6) {
      this.showStage = 7
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(0, 4.8, -40)))
      this.audio.boom(0.7)
      this.pushHud()
    }
    if (t > 21 && this.showStage === 7) {
      this.showStage = 8
      this.cb.onToast('灯会还在继续，慢慢逛')
      this.pushHud()
    }

    this.towerPulse = t < 1.2 ? t / 1.2 : Math.max(0.25, 1 - (t - 1.2) / 24)
    for (const s of this.towerGlow) {
      s.material.opacity = Math.min(0.95, 0.16 + this.towerPulse * 1.5)
      s.scale.setScalar(5.2 + this.towerPulse * 5)
    }
    if (t > 26) {
      this.showClock = -1
      this.showStage = 0
      this.towerPulse = 0
      for (const s of this.towerGlow) {
        s.material.opacity = 0.16
        s.scale.setScalar(5.2)
      }
      this.pushHud()
    }
  }

  /**
   * Distant festival fireworks between shows.  One shell at a time, high over
   * the far banks, so the sky keeps moving without stealing the show's beat.
   */
  private updateAmbientFireworks(dt: number) {
    if (this.showClock >= 0) return
    this.nextFirework -= dt
    if (this.nextFirework > 0) return
    this.nextFirework = 8 + Math.random() * 9
    const palette = [0xffc07a, 0xff9a6a, 0xff8f9e, 0xffd8a8, 0x9fd8ff]
    const color = palette[Math.floor(Math.random() * palette.length)]
    // Place the shell ahead of the player so the beat always lands in frame.
    const dist = 70 + Math.random() * 45
    const side = (Math.random() - 0.5) * 60
    const x = this.player.x + Math.cos(this.yaw) * dist - Math.sin(this.yaw) * side
    const z = this.player.z + Math.sin(this.yaw) * dist + Math.cos(this.yaw) * side
    const y = 32 + Math.random() * 16
    this.effects.push(
      new ParticleBurst(this.scene, this.glow, new THREE.Vector3(x, y, z), {
        count: 560,
        color,
        spread: 1.4,
        speed: 10.5,
        size: 2.2,
        life: 2.8,
        gravity: 1.6,
        shell: true,
      }),
    )
  }

  private updateEffects(dt: number) {
    for (let i = this.effects.length - 1; i >= 0; i--) {
      if (!this.effects[i].update(dt)) {
        this.effects[i].dispose(this.scene)
        this.effects.splice(i, 1)
      }
    }
  }

  private updateNearby() {
    let best: InteractableId | null = null
    let bestD = Infinity
    for (const it of INTERACTABLES) {
      const d = Math.hypot(this.player.x - it.pos[0], -this.player.z - it.pos[1])
      if (d < it.radius && d < bestD) {
        bestD = d
        best = it.id
      }
    }
    if (best !== this.nearby) {
      this.nearby = best
      const it = INTERACTABLES.find((i) => i.id === best)
      this.cb.onPrompt(it ? { id: it.id, label: it.label } : null)
    }
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.canvas.removeEventListener('pointerdown', this.onPointerDown)
    this.canvas.removeEventListener('pointermove', this.onPointerMove)
    window.removeEventListener('pointerup', this.onPointerUp)
    window.removeEventListener('keydown', this.onKeyDown)
    window.removeEventListener('keyup', this.onKeyUp)
    window.removeEventListener('resize', this.resize)
    document.removeEventListener('pointerlockchange', this.onLockChange)
    this.effects.forEach((e) => {
      e.dispose(this.scene)
    })
    this.atmosphere.dispose(this.scene)
    this.flora?.dispose()
    this.audio.dispose()
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (mesh.isMesh) {
        mesh.geometry?.dispose()
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        mats.forEach((m) => {
          m?.dispose()
        })
      }
    })
    this.environmentMap?.dispose()
    this.composer.dispose()
    this.renderer.dispose()
  }
}
