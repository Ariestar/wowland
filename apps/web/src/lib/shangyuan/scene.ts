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
import { CatPrototype } from './cat'
import { type CollisionLayout, ObstacleField, WalkableGround } from './collision'
import {
  BLESSINGS,
  CAT_ZONE,
  COPY,
  INTERACTABLES,
  type InteractableId,
  LANTERN_STYLES,
  RELEASE,
  RIDDLE,
  SCENE,
  VIEWPOINTS,
} from './data'
import { type Effect, Ripple, RiverAtmosphere } from './effects'
import { FireworkShell, FireworkSystem, IronFlower, type ShellKind } from './fireworks'
import { WaterlineFlora } from './flora'
import { gradingShader, sanitizeShader } from './postFx'
import type { Panel, Phase, Prompt, SceneCallbacks } from './types'
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
const UP = new THREE.Vector3(0, 1, 0)

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

/**
 * The river lanterns all share three small templates.  Cloning them produced
 * one draw call per part per lantern; an InstancedMesh per template part keeps
 * the same geometry, materials and per-lantern transforms in a single call.
 */
type LanternBatch = {
  parts: {
    geometry: THREE.BufferGeometry
    material: THREE.Material
    matrix: THREE.Matrix4
  }[]
  meshes: THREE.InstancedMesh[]
  active: number
}

type LanternRecord = {
  batch: LanternBatch
  t: number
  speed: number
  lane: number
  x: number
  y: number
  z: number
  yaw: number
  scale: number
  /** A player-released lantern: slides in, glows, then fades and recycles. */
  owner: boolean
  /** Wall-clock birth (performance.now), so lifetime survives FPS dips. */
  born: number
  /** Shore-side x the owner lantern slides in from. */
  shoreX: number
}

/** Constants for the owner-lantern slide-in (PRD §7.4: 0.3–1.5 s). */
const SLIDE_TIME = 1.1
const SHORE_X = 13.0
const WATER_X = 11.2
/** Quay release point in Blender coords (x, y); the lantern enters here. */
const RELEASE_SPOT = { x: 13.5, y: -86.4 }

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
  private readonly fireworks: FireworkSystem
  private skyLanterns: {
    points: THREE.Points
    positions: Float32Array
    speeds: Float32Array
    phases: Float32Array
    drifts: Float32Array
  } | null = null
  private towerGlowMaterial: THREE.PointsMaterial | null = null
  private claimLanternMat: THREE.MeshStandardMaterial | null = null
  private markerLanternMat: THREE.MeshStandardMaterial | null = null
  private claimAnim = -1
  /** Floating blessing text above each fresh lantern (PRD §7.4). */
  private blessings: { sprite: THREE.Sprite; born: number }[] = []
  private readonly wheelPivots: THREE.Object3D[] = []
  private readonly lanternBatches = new Map<string, LanternBatch>()
  private lanternHalo: THREE.Points | null = null
  private readonly lanternHaloPositions = new Float32Array(70 * 3)
  /** Extra bright halo over fresh player lanterns (PRD §7.4 identification). */
  private ownerGlow: THREE.Points | null = null
  private readonly ownerGlowPositions = new Float32Array(5 * 3)
  private readonly lanternMatrix = new THREE.Matrix4()
  private readonly lanternPartMatrix = new THREE.Matrix4()
  private readonly lanternQuat = new THREE.Quaternion()
  private readonly lanternPos = new THREE.Vector3()
  private readonly lanternScale = new THREE.Vector3()
  private readonly lanterns: LanternRecord[] = []
  private readonly effects: Effect[] = []

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
  private claimed = false
  private riddleSolved = false
  private released = false
  private releaseCount = 0
  /** Wall-clock timestamp; releases are allowed again after it (PRD §7.5). */
  private cooldownUntil = 0
  private cooldownShown = 0
  private releasing = false
  private draftStyle = 0
  private draftBlessing = 0
  private showStarted = false
  private releaseAnim: {
    t: number
    styleIdx: number
    blessing: string
    spawned: boolean
  } | null = null
  private style = ''
  private blessing = ''
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

  // --- G0 cat prototype (PRD §8): placeholder geometry, isolated state.
  private cat: CatPrototype | null = null
  private catMode = false
  private catEnterT = 1
  private catCompleted = false
  private catSaved: {
    pos: THREE.Vector3
    yaw: number
    pitch: number
    ground: number
  } | null = null
  private catActionLabel = ''

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
    this.fireworks = new FireworkSystem(this.glow)
    this.scene.add(this.fireworks.object)
    // Five bright discs over the freshest player lanterns.
    const ownerGlowGeo = new THREE.BufferGeometry()
    const ownerGlowAttr = new THREE.BufferAttribute(this.ownerGlowPositions, 3)
    ownerGlowAttr.setUsage(THREE.DynamicDrawUsage)
    ownerGlowGeo.setAttribute('position', ownerGlowAttr)
    ownerGlowGeo.setDrawRange(0, 0)
    this.ownerGlow = new THREE.Points(
      ownerGlowGeo,
      new THREE.PointsMaterial({
        map: this.glow,
        color: 0xffd9a0,
        transparent: true,
        opacity: 0.45,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        size: this.spriteSize(0.5),
        sizeAttenuation: true,
      }),
    )
    this.ownerGlow.frustumCulled = false
    this.ownerGlow.userData.noGtao = true
    this.scene.add(this.ownerGlow)
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
      // GTAOPass hides points and lines from its normal prepass but not
      // sprites.  A sprite quad writes depth for its whole rectangle, which
      // shows up as a black slab behind the tower and as square bats in the
      // sky, so extend the same hide/restore list to sprites.
      const internals = gtao as unknown as {
        _overrideVisibility: () => void
        _visibilityCache: THREE.Object3D[]
      }
      const overrideVisibility = internals._overrideVisibility.bind(gtao)
      internals._overrideVisibility = () => {
        overrideVisibility()
        this.scene.traverse((o) => {
          const sprite = o as THREE.Sprite
          if ((sprite.isSprite || o.userData.noGtao) && o.visible) {
            o.visible = false
            internals._visibilityCache.push(o)
          }
        })
      }
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
    // Photo mode accepts no scene input (PRD §7.6); the tap itself is the
    // mobile exit, handled by the component, and must not grab the pointer.
    if (this.photo) return
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
      if (this.catMode) this.exitCat()
      else this.closePanel()
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
    const total = 6
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
      // The exported level never moves, so its transform hierarchy can skip
      // the per-frame matrix sweep; only the water, lanterns and FX animate.
      world.traverse((o) => {
        o.matrixAutoUpdate = false
        o.updateMatrix()
      })
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
      this.buildLanternBatch(id, gltf.scene)
      tick()
    })

    await Promise.all([layoutJob, worldJob, ...templateJobs])
    this.addGroundGlow()
    this.seedAmbientLanterns()
    this.buildCat()
    this.buildMvpProps()
    tick()
    this.pushHud()
    this.worldReady = true
    this.cb.onReady()
    this.loop()
  }

  /**
   * Placeholder props for the MVP fragment (G0/G1): the claimable paper
   * lantern at the paifang, the stall marker lamp, and the faint release
   * marker at the quay.  Real assets replace these per A03/A06/A09.
   */
  private buildMvpProps() {
    const paper = (opacity: number) =>
      new THREE.MeshStandardMaterial({
        color: 0xf6e6c8,
        roughness: 0.7,
        emissive: new THREE.Color(0xffb45e),
        emissiveIntensity: opacity,
        transparent: true,
        opacity: 0.94,
      })

    // A03 claim lantern: unlit until the player claims it (PRD §5.1).
    const claimMat = paper(0.06)
    this.claimLanternMat = claimMat
    const lanternGeo = new THREE.CylinderGeometry(0.16, 0.16, 0.34, 10)
    const claimLantern = new THREE.Mesh(lanternGeo, claimMat)
    claimLantern.position.set(15.6, SCENE.groundZ + 1.05, 122.4)
    claimLantern.castShadow = true
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.055, 1.6, 8),
      new THREE.MeshStandardMaterial({ color: 0x4a3826, roughness: 0.9 }),
    )
    pole.position.set(15.6, SCENE.groundZ + 0.8, 122.55)
    pole.castShadow = true
    this.scene.add(claimLantern, pole)

    // A06 riddle marker lamp: dim until the riddle is solved (PRD §6.1).
    const markerMat = paper(0.08)
    this.markerLanternMat = markerMat
    const marker = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), markerMat)
    marker.position.set(16.0, SCENE.groundZ + 0.85, 106.0)
    const markerPole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.045, 0.9, 8),
      new THREE.MeshStandardMaterial({ color: 0x4a3826, roughness: 0.9 }),
    )
    markerPole.position.set(16.0, SCENE.groundZ + 0.45, 106.0)
    this.scene.add(marker, markerPole)

    // A09 release marker: a faint ground decal at the safe stand (PRD §7.1).
    const decalMat = new THREE.MeshBasicMaterial({
      map: this.glow,
      color: 0xffc477,
      transparent: true,
      opacity: 0.2,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const decal = new THREE.Mesh(new THREE.CircleGeometry(0.8, 24), decalMat)
    decal.rotation.x = -Math.PI / 2
    decal.position.set(RELEASE_SPOT.x, SCENE.groundZ + 0.04, -RELEASE_SPOT.y)
    this.scene.add(decal)
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
    // Five halo tiers used to be five sprites, i.e. five draw calls for a
    // single soft glow.  One Points cloud keeps the same screen-facing discs
    // and lets the show pulse all of them through one material.
    const tiers = [5, 10, 16, 22, 28]
    const positions = new Float32Array(tiers.length * 3)
    tiers.forEach((y, i) => {
      positions[i * 3] = 0
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = -78
    })
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    this.towerGlowMaterial = new THREE.PointsMaterial({
      map: this.glow,
      color: 0xffc98a,
      transparent: true,
      opacity: 0.12,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      size: this.spriteSize(6.2),
      sizeAttenuation: true,
    })
    const points = new THREE.Points(geometry, this.towerGlowMaterial)
    points.frustumCulled = false
    points.userData.noGtao = true
    this.scene.add(points)
  }

  /** Points size that covers the same world height as a Sprite of this scale. */
  private spriteSize(worldSize: number): number {
    return worldSize / Math.tan(THREE.MathUtils.degToRad(this.camera.fov * 0.5))
  }

  /** Warm pools on the paving: cheap, and they do most of the "lit street" work. */
  private addGroundGlow() {
    const pools: [number, number, number, number][] = []
    for (let y = -126; y <= 162; y += 16) {
      pools.push([16.4, y, 7, 0.16])
      pools.push([-16.4, y + 8, 7, 0.1])
    }
    pools.push([0, 10, 12, 0.28])
    pools.push([0, 78, 16, 0.22])

    // One mesh with a vertex-colour alpha carries every pool, so the street
    // lighting costs a single draw call instead of one per pool.
    const plane = new THREE.PlaneGeometry(1, 1)
    const srcPos = plane.attributes.position
    const srcUv = plane.attributes.uv
    const srcIndex = plane.index
    if (!srcIndex) {
      plane.dispose()
      return
    }
    const positions: number[] = []
    const uvs: number[] = []
    const colors: number[] = []
    const indices: number[] = []
    const tint = new THREE.Color(0xffb877)
    const matrix = new THREE.Matrix4()
    const quat = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0))
    const vertex = new THREE.Vector3()
    for (const [x, y, size, opacity] of pools) {
      const base = positions.length / 3
      matrix.compose(
        new THREE.Vector3(x, SCENE.groundZ + 0.03, -y),
        quat,
        new THREE.Vector3(size, size, 1),
      )
      for (let i = 0; i < srcPos.count; i++) {
        vertex.fromBufferAttribute(srcPos, i).applyMatrix4(matrix)
        positions.push(vertex.x, vertex.y, vertex.z)
        uvs.push(srcUv.getX(i), srcUv.getY(i))
        colors.push(tint.r, tint.g, tint.b, opacity)
      }
      for (let i = 0; i < srcIndex.count; i++) indices.push(srcIndex.getX(i) + base)
    }
    plane.dispose()

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 4))
    geometry.setIndex(indices)
    const material = new THREE.MeshBasicMaterial({
      map: this.glow,
      color: 0xffffff,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const mesh = new THREE.Mesh(geometry, material)
    this.scene.add(mesh)
  }

  private buildLanternBatch(id: string, template: THREE.Object3D) {
    template.updateMatrixWorld(true)
    const inverse = template.matrixWorld.clone().invert()
    const parts: LanternBatch['parts'] = []
    template.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      parts.push({
        geometry: mesh.geometry,
        material: mesh.material as THREE.Material,
        matrix: new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld),
      })
    })
    const meshes = parts.map((part) => {
      const mesh = new THREE.InstancedMesh(part.geometry, part.material, 70)
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      mesh.count = 0
      // Instances span the whole canal, so a single bounding sphere would
      // always pass; one draw call is cheaper than a stale cull test.
      mesh.frustumCulled = false
      mesh.castShadow = false
      mesh.receiveShadow = false
      mesh.matrixAutoUpdate = false
      mesh.updateMatrix()
      this.scene.add(mesh)
      return mesh
    })
    this.lanternBatches.set(id, { parts, meshes, active: 0 })
    this.ensureLanternHalo()
  }

  private ensureLanternHalo() {
    if (this.lanternHalo) return
    const geometry = new THREE.BufferGeometry()
    const attribute = new THREE.BufferAttribute(this.lanternHaloPositions, 3)
    attribute.setUsage(THREE.DynamicDrawUsage)
    geometry.setAttribute('position', attribute)
    geometry.setDrawRange(0, 0)
    this.lanternHalo = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        map: this.glow,
        color: 0xffc477,
        transparent: true,
        opacity: 0.3,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        size: this.spriteSize(1.05),
        sizeAttenuation: true,
      }),
    )
    this.lanternHalo.frustumCulled = false
    this.lanternHalo.userData.noGtao = true
    this.scene.add(this.lanternHalo)
  }

  private seedAmbientLanterns() {
    for (let i = 0; i < 26; i++) {
      const style = i % 4 === 0 ? 'model-river-lantern-paperboat' : 'model-river-lantern-lotus'
      const lane = ((i * 7) % 17) - 8
      this.spawnLantern(style, lane, -128 + i * 11.6, 0.32 + (i % 4) * 0.08)
    }
  }

  private spawnLantern(
    style: string,
    x: number,
    z: number,
    speed: number,
    ripple = false,
    owner = false,
  ) {
    const batch = this.lanternBatches.get(style)
    if (!batch) return
    this.lanterns.push({
      batch,
      t: Math.random() * 10,
      speed,
      // The lane is the cross-canal coordinate the lantern drifts around.
      lane: x,
      x,
      y: 0.08,
      z,
      yaw: 0,
      scale: 0.9 + Math.random() * 0.35,
      owner,
      born: performance.now(),
      shoreX: SHORE_X,
    })
    if (ripple) this.effects.push(new Ripple(this.scene, new THREE.Vector3(x, 0, z)))
    if (this.lanterns.length > 70) {
      // Drop the oldest environment lantern; player lanterns stay capped by
      // their own release limit, so never evict those.
      const index = this.lanterns.findIndex((l) => !l.owner)
      if (index >= 0) this.lanterns.splice(index, 1)
    }
  }

  // ---------------------------------------------------------------- interaction

  interact() {
    if (this.photo) return
    if (this.catMode) {
      this.catAction()
      return
    }
    if (this.panel) return
    const id = this.nearby
    if (!id) return
    this.audio.unlock()
    switch (id) {
      case 'entrance':
        if (this.claimed) {
          this.cb.onToast(COPY.claimedAgain)
          return
        }
        this.openPanel({
          kind: 'claim',
          title: '灯门',
          body: '守灯人递来一盏素纸花灯。「提着它，去灯谜摊猜一道谜。」',
          options: [{ label: COPY.C02 }],
        })
        return
      case 'riddle':
        if (!this.claimed) {
          this.cb.onToast(COPY.riddleLocked)
          return
        }
        if (this.riddleSolved) {
          this.cb.onToast(COPY.riddleDone)
          return
        }
        this.openPanel({
          kind: 'riddle',
          title: '灯谜 · 一谜一灯',
          body: RIDDLE.question,
          options: RIDDLE.options.map((label) => ({ label })),
        })
        return
      case 'quay':
        if (!this.riddleSolved) {
          this.cb.onToast(COPY.quayLocked)
          return
        }
        if (this.releasing) {
          this.cb.onToast(COPY.releaseBusy)
          return
        }
        if (this.cooldownSeconds() > 0) {
          this.cb.onToast(COPY.C14(Math.ceil(this.cooldownSeconds())))
          return
        }
        if (this.activeOwnerCount() >= RELEASE.maxActive) {
          this.cb.onToast(COPY.C13)
          return
        }
        this.openReleasePanel()
        return
      case 'catMask':
        if (!this.claimed) {
          this.cb.onToast(COPY.C16)
          return
        }
        this.enterCat()
        return
    }
  }

  private openPanel(panel: Panel) {
    this.panel = panel
    this.cb.onPanel(panel)
  }

  private openReleasePanel() {
    this.openPanel({
      kind: 'release',
      title: '埠头 · 选一盏灯，留一句愿',
      body: '挑一盏河灯，留一句祝词，然后把它放进河里。',
      options: LANTERN_STYLES.map((s) => ({ label: s.name, note: s.meaning })),
      selectedStyle: this.draftStyle,
      selectedBlessing: this.draftBlessing,
      confirmLabel: COPY.C10,
    })
  }

  selectStyle(index: number) {
    if (this.panel?.kind !== 'release') return
    if (index < 0 || index >= LANTERN_STYLES.length) return
    this.draftStyle = index
    this.audio.chime(720)
    this.panel = { ...this.panel, selectedStyle: index }
    this.cb.onPanel(this.panel)
  }

  selectBlessing(index: number) {
    if (this.panel?.kind !== 'release') return
    if (index < 0 || index >= BLESSINGS.length) return
    this.draftBlessing = index
    this.audio.chime(760)
    this.panel = { ...this.panel, selectedBlessing: index }
    this.cb.onPanel(this.panel)
  }

  /** PRD §7.4: guards, then the slide-in plays out in update(). */
  confirmRelease() {
    if (this.panel?.kind !== 'release') return
    if (this.releasing) {
      this.cb.onToast(COPY.releaseBusy)
      return
    }
    if (this.cooldownSeconds() > 0) {
      this.cb.onToast(COPY.C14(Math.ceil(this.cooldownSeconds())))
      return
    }
    if (this.activeOwnerCount() >= RELEASE.maxActive) {
      this.cb.onToast(COPY.C13)
      return
    }
    // The player must still stand in the safe range.
    const quay = INTERACTABLES.find((i) => i.id === 'quay')
    if (
      !quay ||
      Math.hypot(this.player.x - quay.pos[0], -this.player.z - quay.pos[1]) > quay.radius + 0.6
    ) {
      this.cb.onToast('请站回埠头的放灯位置。')
      return
    }
    const style = LANTERN_STYLES[this.draftStyle]
    const blessing = BLESSINGS[this.draftBlessing]
    this.style = style.name
    this.blessing = blessing
    this.releasing = true
    this.closePanel()
    this.releaseAnim = { t: 0, styleIdx: this.draftStyle, blessing, spawned: false }
    this.pushHud()
  }

  choose(index: number) {
    const panel = this.panel
    if (!panel) return
    const option = panel.options[index]
    if (!option || option.disabled) return

    if (panel.kind === 'claim') {
      this.claimed = true
      this.claimAnim = 0
      this.audio.chime(660)
      this.cb.onToast(COPY.C03)
      this.closePanel()
      this.pushHud()
      return
    }

    if (panel.kind === 'riddle') {
      if (index === RIDDLE.answer) {
        this.riddleSolved = true
        this.audio.chime(880)
        this.cb.onToast(COPY.C07)
        this.closePanel()
        this.pushHud()
      } else {
        this.panel = { ...panel, hint: COPY.C06 }
        this.cb.onPanel(this.panel)
        this.audio.thud()
      }
      return
    }

    if (panel.kind === 'release') {
      // Compatibility path: the component drives selection directly.
      if (index < LANTERN_STYLES.length) this.selectStyle(index)
      else this.selectBlessing(index - LANTERN_STYLES.length)
      return
    }

    this.closePanel()
  }

  private activeOwnerCount(): number {
    return this.lanterns.reduce(
      (n, l) => (l.owner && this.ownerAge(l) < RELEASE.lifetime ? n + 1 : n),
      0,
    )
  }

  /** Seconds left before another release is allowed (wall clock). */
  private cooldownSeconds(): number {
    return Math.max(0, (this.cooldownUntil - performance.now()) / 1000)
  }

  /** Owner-lantern age in seconds, tracked on the wall clock. */
  private ownerAge(l: LanternRecord): number {
    return (performance.now() - l.born) / 1000
  }

  private spawnOwnerLantern(styleIdx: number) {
    const style = LANTERN_STYLES[styleIdx]
    const id = style?.file ?? 'model-river-lantern-lotus'
    const z = -RELEASE_SPOT.y
    this.spawnLantern(
      id,
      WATER_X,
      z,
      RELEASE.speedMin + Math.random() * (RELEASE.speedMax - RELEASE.speedMin),
      true,
      true,
    )
  }

  private startShow() {
    if (this.showStarted) return
    this.showStarted = true
    this.showClock = 0
    this.showStage = 0
    this.autoShow = -1
    this.pushHud()
    this.cb.onToast('灯会开始了，抬头看看')
  }

  closePanel() {
    if (!this.panel) return
    this.panel = null
    this.cb.onPanel(null)
  }

  private pushHud() {
    this.cb.onHud({
      phase: this.phase,
      claimed: this.claimed,
      riddleSolved: this.riddleSolved,
      released: this.released,
      releasedCount: this.releaseCount,
      activeLanterns: this.activeOwnerCount(),
      cooldown: Math.ceil(this.cooldownSeconds()),
      style: this.style,
      blessing: this.blessing,
      showActive: this.showStage > 0 && this.showStage < 5,
      cat: {
        active: this.catMode,
        basketTipped: this.cat?.tipped ?? false,
        onShed: this.cat?.landed ?? false,
        completed: this.catCompleted,
        action: this.catActionLabel,
      },
    })
  }

  // ---------------------------------------------------------------- cat mode

  enterCat() {
    if (this.catMode || !this.cat) return
    if (this.panel || this.releasing) return
    this.catSaved = {
      pos: this.player.clone(),
      yaw: this.yaw,
      pitch: this.pitch,
      ground: this.playerGround,
    }
    this.catMode = true
    this.catEnterT = 0
    this.cat.reset()
    this.viewTween = null
    this.pan = null
    this.cb.onToast(COPY.C17)
    this.pushHud()
  }

  exitCat() {
    if (!this.catMode) return
    this.catMode = false
    this.catEnterT = 1
    const saved = this.catSaved
    if (saved) {
      this.player.copy(saved.pos)
      this.playerGround = saved.ground
      this.yaw = saved.yaw
      this.pitch = saved.pitch
      this.camera.position.copy(this.player)
    }
    this.catSaved = null
    this.setTouch(0, 0)
    this.keys.clear()
    this.cb.onToast('回到人形，进度保留。')
    this.pushHud()
  }

  /** Reset the current attempt: basket upright, cat back to the mat. */
  resetCatAttempt() {
    if (!this.catMode || !this.cat) return
    this.cat.reset()
    this.pushHud()
  }

  catAction() {
    if (!this.catMode || !this.cat) return
    this.audio.unlock()
    this.cat.act()
  }

  private onCatActionChange(action: string) {
    this.catActionLabel = action
    this.pushHud()
  }

  private buildCat() {
    this.cat = new CatPrototype(CAT_ZONE, SCENE.groundZ, {
      onBasketTipped: () => {
        this.audio.thud()
        this.cb.onToast(COPY.C19)
        this.pushHud()
      },
      onShedLanded: () => {
        this.catCompleted = true
        this.audio.chime(980)
        this.cb.onToast(COPY.C22)
        this.pushHud()
      },
      onActionChange: (action) => this.onCatActionChange(action),
    })
    this.cat.group.visible = false
    this.scene.add(this.cat.group)
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
      playerLanterns: this.activeOwnerCount(),
      obstacles: this.obstacleField ? this.layout?.obstacles.length : 0,
      ground: +this.playerGround.toFixed(2),
      reflection: Boolean(this.reflectionTarget),
      phase: this.phase,
      claimed: this.claimed,
      riddleSolved: this.riddleSolved,
      released: this.released,
      releaseCount: this.releaseCount,
      cooldown: Math.round(this.cooldownSeconds() * 10) / 10,
      catMode: this.catMode,
      catCompleted: this.catCompleted,
      catTipped: this.cat?.tipped ?? false,
      catOnShed: this.cat?.landed ?? false,
      showStage: this.showStage,
    }
  }

  /** PRD §4.3: restore the position without touching session progress. */
  returnToEntrance() {
    if (this.catMode) this.exitCat()
    const spawn = this.layout?.spawn ?? { x: 16.21, y: -132 }
    this.teleport(spawn.x, spawn.y)
    this.cb.onToast(COPY.C24)
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
    if (this.catMode && this.cat) {
      // Steer the cat instead of the parked human camera.
      const p = this.cat.position
      const dx = x - p.x
      const dz = -y - p.z
      this.cat.face(Math.atan2(dz, dx))
      return
    }
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
    if (this.photo && document.pointerLockElement) {
      // Framing mode needs the cursor for the exit tap (PRD §7.6).
      document.exitPointerLock?.()
      this.pointerLocked = false
    }
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
    if (this.catMode && this.cat) {
      this.updateCatFrame(dt)
    } else {
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
    }

    this.waterMat.uniforms.uTime.value += dt
    this.atmosphere.update(dt, this.camera)
    this.flora?.update(dt)
    this.grading.uniforms.uTime.value += dt

    for (const wheel of this.wheelPivots) wheel.rotation.z += dt * 0.24

    this.updateLanterns(dt)
    this.updateSkyLanterns(dt)
    this.fireworks.update(dt)
    this.updateShow(eventDt)
    this.updateAmbientFireworks(dt)
    this.updateEffects(dt)
    this.updateNearby()
    this.updateRelease(eventDt)
    this.updateProps(dt)
  }

  /** Lamp state ramps: the claim lantern lights over ~1 s (PRD §5.2). */
  private updateProps(dt: number) {
    if (this.claimAnim >= 0 && this.claimAnim < 1.1) {
      this.claimAnim += dt
      const t = Math.min(1, this.claimAnim / 1.0)
      if (this.claimLanternMat) this.claimLanternMat.emissiveIntensity = 0.06 + t * 1.7
    }
    if (
      this.riddleSolved &&
      this.markerLanternMat &&
      this.markerLanternMat.emissiveIntensity < 1.5
    ) {
      this.markerLanternMat.emissiveIntensity = Math.min(
        1.5,
        this.markerLanternMat.emissiveIntensity + dt * 1.5,
      )
    }
    // Blessing text rises a little and fades after ~3.2 s.
    for (let i = this.blessings.length - 1; i >= 0; i--) {
      const b = this.blessings[i]
      const age = (performance.now() - b.born) / 1000
      b.sprite.position.y += dt * 0.18
      const mat = b.sprite.material as THREE.SpriteMaterial
      mat.opacity = Math.max(0, 1 - age / 3.2) * 0.95
      if (age > 3.2) {
        this.scene.remove(b.sprite)
        mat.map?.dispose()
        mat.dispose()
        this.blessings.splice(i, 1)
      }
    }
  }

  /** Draw the blessing on a canvas sprite and float it over a new lantern. */
  private spawnBlessing(text: string, x: number, z: number) {
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 128
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.font = '52px "SJR Display", serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = 'rgba(255, 224, 176, 0.96)'
    ctx.shadowColor = 'rgba(255, 170, 90, 0.9)'
    ctx.shadowBlur = 18
    ctx.fillText(text, 256, 64)
    const texture = new THREE.CanvasTexture(canvas)
    texture.colorSpace = THREE.SRGBColorSpace
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthWrite: false,
        opacity: 0.95,
      }),
    )
    sprite.position.set(x, 0.85, z)
    sprite.scale.set(1.5, 0.375, 1)
    sprite.userData.noGtao = true
    this.scene.add(sprite)
    this.blessings.push({ sprite, born: performance.now() })
  }

  /** Cat-mode frame: drive the prototype, follow it with a third-person camera. */
  private updateCatFrame(dt: number) {
    if (!this.cat) return
    const f = (this.keys.has('KeyW') ? 1 : 0) - (this.keys.has('KeyS') ? 1 : 0)
    const r = (this.keys.has('KeyD') ? 1 : 0) - (this.keys.has('KeyA') ? 1 : 0)
    if (this.touchMove || this.touchStrafe) {
      this.cat.setMove(this.touchMove, this.touchStrafe)
    } else {
      this.cat.setMove(this.panel ? 0 : f, this.panel ? 0 : r)
    }
    this.cat.update(dt)
    this.catEnterT = Math.min(1, this.catEnterT + dt / 0.8)
    const eased = this.catEnterT * this.catEnterT * (3 - 2 * this.catEnterT)

    const target = new THREE.Vector3()
    const angles = { yaw: 0, pitch: 0 }
    this.cat.cameraTarget(target, angles)
    const look = this.cat.position.clone()
    look.y += 0.4
    if (this.catEnterT < 1 && this.catSaved) {
      target.lerpVectors(this.catSaved.pos, target, eased)
    }
    this.camera.position.copy(target)
    this.camera.lookAt(look)
    // The human position stays parked in catSaved so returning to human mode
    // restores it exactly; only the camera follows the cat.
    this.yaw = angles.yaw
    this.pitch = angles.pitch
  }

  /** Release animation clock (PRD §7.4): 0.3 s pause, then the slide-in. */
  private updateRelease(dt: number) {
    // Keep the HUD countdown fresh without re-rendering every frame.
    if (this.cooldownUntil > 0) {
      const secs = Math.ceil(this.cooldownSeconds())
      if (secs <= 0) {
        this.cooldownUntil = 0
        this.cooldownShown = 0
        this.pushHud()
      } else if (secs !== this.cooldownShown) {
        this.cooldownShown = secs
        this.pushHud()
      }
    }

    const anim = this.releaseAnim
    if (!anim) return
    anim.t += dt
    if (!anim.spawned && anim.t >= 0.3) {
      anim.spawned = true
      this.spawnOwnerLantern(anim.styleIdx)
    }
    if (anim.spawned && anim.t >= 0.3 + SLIDE_TIME) {
      this.audio.splash()
      this.effects.push(new Ripple(this.scene, new THREE.Vector3(WATER_X, 0, -RELEASE_SPOT.y)))
      this.spawnBlessing(anim.blessing, WATER_X, -RELEASE_SPOT.y)
      this.releaseCount++
      this.cooldownUntil = performance.now() + RELEASE.cooldown * 1000
      this.releasing = false
      this.releaseAnim = null
      if (!this.released) {
        this.released = true
        this.phase = 'released'
        this.cb.onToast(`心愿已入河 ·「${anim.blessing}」`)
        this.cb.onToast(COPY.C11)
        // The first success starts the show once, 3–5 s later (PRD §7.6).
        this.autoShow = 3.5
      } else {
        this.cb.onToast(`又一盏灯入了河 ·「${anim.blessing}」`)
      }
      this.pushHud()
    }
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
    // Owner lanterns slide in from the shore, glow for identification, then
    // fade and recycle after their lifetime (PRD §7.4/§7.5).  Ages use the
    // wall clock so FPS dips cannot stretch the rules.
    for (let i = this.lanterns.length - 1; i >= 0; i--) {
      const l = this.lanterns[i]
      if (!l.owner) continue
      if (this.ownerAge(l) > RELEASE.lifetime) {
        this.lanterns.splice(i, 1)
      }
    }

    const xs = this.waterMat.uniforms.uLanternX.value as Float32Array
    const zs = this.waterMat.uniforms.uLanternZ.value as Float32Array
    const is = this.waterMat.uniforms.uLanternI.value as Float32Array
    xs.fill(0)
    zs.fill(0)
    is.fill(0)
    for (const batch of this.lanternBatches.values()) batch.active = 0
    let ownerGlowCount = 0
    for (let i = 0; i < this.lanterns.length; i++) {
      const l = this.lanterns[i]
      l.t += dt
      l.z += l.speed * dt
      l.x = l.lane + Math.sin(l.t * 0.7) * 0.55
      l.y = 0.08 + Math.sin(l.t * 1.6) * 0.03
      l.yaw = Math.sin(l.t * 0.4) * 0.3
      if (l.z > 182) {
        l.z = -140
        l.t = Math.random() * 6
      }
      if (l.owner) {
        const age = this.ownerAge(l)
        // Slide from the quay edge onto the water during the first second.
        const slide = Math.min(1, age / SLIDE_TIME)
        const eased = slide * slide * (3 - 2 * slide)
        l.x = l.shoreX + (l.lane - l.shoreX) * eased + Math.sin(l.t * 0.7) * 0.55 * slide
        l.y = 0.08 + (1 - slide) * 0.32 + Math.sin(l.t * 1.6) * 0.03 * slide
        // Fade out over the last three seconds of the lifetime.
        const remain = RELEASE.lifetime - age
        if (remain < 3) l.scale = Math.max(0.02, (remain / 3) * 0.9)
      }
      const batch = l.batch
      const slot = batch.active++
      this.lanternPos.set(l.x, l.y, l.z)
      this.lanternQuat.setFromAxisAngle(UP, l.yaw)
      this.lanternScale.setScalar(l.scale)
      this.lanternMatrix.compose(this.lanternPos, this.lanternQuat, this.lanternScale)
      for (let p = 0; p < batch.meshes.length; p++) {
        this.lanternPartMatrix.multiplyMatrices(this.lanternMatrix, batch.parts[p].matrix)
        batch.meshes[p].setMatrixAt(slot, this.lanternPartMatrix)
      }
      this.lanternHaloPositions[i * 3] = l.x
      this.lanternHaloPositions[i * 3 + 1] = 0.5
      this.lanternHaloPositions[i * 3 + 2] = l.z
      if (i < 12) {
        xs[i] = l.x
        zs[i] = l.z
        is[i] = 0.8 + 0.2 * Math.sin(l.t * 2)
      }
      // Fresh owner lanterns keep a brighter identification glow.
      if (l.owner && this.ownerAge(l) < RELEASE.glowTime && ownerGlowCount < 5) {
        this.ownerGlowPositions[ownerGlowCount * 3] = l.x
        this.ownerGlowPositions[ownerGlowCount * 3 + 1] = 0.55
        this.ownerGlowPositions[ownerGlowCount * 3 + 2] = l.z
        ownerGlowCount++
      }
    }
    for (const batch of this.lanternBatches.values()) {
      for (const mesh of batch.meshes) {
        mesh.count = batch.active
        mesh.instanceMatrix.needsUpdate = true
      }
    }
    if (this.lanternHalo) {
      const position = this.lanternHalo.geometry.getAttribute('position') as THREE.BufferAttribute
      position.needsUpdate = true
      this.lanternHalo.geometry.setDrawRange(0, this.lanterns.length)
    }
    if (this.ownerGlow) {
      const position = this.ownerGlow.geometry.getAttribute('position') as THREE.BufferAttribute
      position.needsUpdate = true
      this.ownerGlow.geometry.setDrawRange(0, ownerGlowCount)
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
      // The MVP show plays across the canal from the release quay, so the
      // pan frames it from the fragment (PRD §7.6).
      this.panTo(new THREE.Vector3(-14, 7, 94), 1.8)
      for (let i = 0; i < 14; i++) {
        this.spawnLantern(
          i % 3 === 0 ? 'model-river-lantern-fish' : 'model-river-lantern-lotus',
          -this.riverHalf * 0.72 + (i % 5) * this.riverHalf * 0.36,
          84 + i * 4.2,
          0.3 + (i % 3) * 0.12,
        )
      }
      this.pushHud()
    }
    if (t > 1.2 && this.showStage === 1) {
      this.showStage = 2
      this.audio.boom(0.85)
      this.effects.push(new IronFlower(this.scene, this.fireworks, new THREE.Vector3(-14, 3.6, 94)))
      this.pushHud()
    }
    if (t > 2.6 && this.showStage === 2) {
      this.showStage = 3
      this.effects.push(
        new FireworkShell(this.scene, this.fireworks, {
          from: new THREE.Vector3(-10, 2.5, 90),
          to: new THREE.Vector3(-10, 22, 90),
          kind: 'peony',
          color: 0xffc07a,
          radius: 20,
          life: 2.6,
          count: 560,
          onLaunch: () => this.audio.whistle(1.05),
          onBurst: () => {
            this.audio.boom(0.5)
            this.audio.crackle(0.5)
          },
        }),
      )
      this.pushHud()
    }
    if (t > 5.0 && this.showStage === 3) {
      this.showStage = 4
      this.effects.push(
        new FireworkShell(this.scene, this.fireworks, {
          from: new THREE.Vector3(-12, 2.5, 92),
          to: new THREE.Vector3(-12, 26, 92),
          kind: 'ring',
          color: 0xff8f60,
          accent: 0xffe3b4,
          radius: 24,
          life: 2.6,
          count: 520,
          onLaunch: () => this.audio.whistle(1.05),
          onBurst: () => this.audio.boom(0.55),
        }),
      )
      this.effects.push(
        new FireworkShell(this.scene, this.fireworks, {
          from: new THREE.Vector3(10, 2.5, 96),
          to: new THREE.Vector3(10, 20, 96),
          kind: 'chrysanthemum',
          color: 0xffdfae,
          radius: 18,
          life: 3.2,
          count: 480,
          ascent: 1.2,
          onLaunch: () => this.audio.whistle(1.2),
          onBurst: () => {
            this.audio.boom(0.4)
            this.audio.crackle(0.7)
          },
        }),
      )
      this.pushHud()
    }
    if (t > 7.4 && this.showStage === 4) {
      this.showStage = 5
      this.cb.onToast('灯会到了最亮的时候')
      this.effects.push(new IronFlower(this.scene, this.fireworks, new THREE.Vector3(-13, 3.6, 92)))
      this.pushHud()
    }
    if (t > 11.5 && this.showStage === 5) {
      this.showStage = 6
      this.effects.push(
        new FireworkShell(this.scene, this.fireworks, {
          from: new THREE.Vector3(-8, 2.5, 90),
          to: new THREE.Vector3(-8, 28, 90),
          kind: 'double',
          color: 0xffd8a8,
          accent: 0x9fd8ff,
          radius: 27,
          life: 2.8,
          count: 620,
          flash: 1.3,
          onLaunch: () => this.audio.whistle(1.05),
          onBurst: () => this.audio.boom(0.65),
        }),
      )
      this.effects.push(
        new FireworkShell(this.scene, this.fireworks, {
          from: new THREE.Vector3(12, 2.5, 94),
          to: new THREE.Vector3(12, 24, 94),
          kind: 'willow',
          color: 0xff9a5a,
          accent: 0xffe3b4,
          radius: 22,
          life: 3.0,
          count: 520,
          ascent: 1.25,
          onLaunch: () => this.audio.whistle(1.25),
          onBurst: () => {
            this.audio.boom(0.5)
            this.audio.crackle(0.9)
          },
        }),
      )
      this.pushHud()
    }
    if (t > 16 && this.showStage === 6) {
      this.showStage = 7
      this.effects.push(new IronFlower(this.scene, this.fireworks, new THREE.Vector3(0, 4.8, 96)))
      this.audio.boom(0.7)
      this.pushHud()
    }
    if (t > 21 && this.showStage === 7) {
      this.showStage = 8
      this.cb.onToast('灯会还在继续，慢慢逛')
      this.pushHud()
    }

    this.towerPulse = t < 1.2 ? t / 1.2 : Math.max(0.25, 1 - (t - 1.2) / 24)
    // A halo behind the tiers, not a lamp in front of them: additive discs
    // at full opacity erase the tower they are meant to light.
    this.setTowerGlow(Math.min(0.32, 0.12 + this.towerPulse * 0.26), 6.2 + this.towerPulse * 2.4)
    if (t > 26) {
      this.showClock = -1
      this.showStage = 0
      this.towerPulse = 0
      this.setTowerGlow(0.12, 6.2)
      this.pushHud()
    }
  }

  private setTowerGlow(opacity: number, size: number) {
    if (!this.towerGlowMaterial) return
    this.towerGlowMaterial.opacity = opacity
    this.towerGlowMaterial.size = this.spriteSize(size)
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
    const palette = [0xffc07a, 0xff9a6a, 0xff8f9e, 0xffd8a8, 0x9fd8ff, 0x9fe8c0, 0xc39bff]
    const kinds: ShellKind[] = [
      'peony',
      'peony',
      'chrysanthemum',
      'willow',
      'ring',
      'double',
      'glitter',
    ]
    const color = palette[Math.floor(Math.random() * palette.length)]
    const kind = kinds[Math.floor(Math.random() * kinds.length)]
    // Place the shell ahead of the player so the beat always lands in frame.
    const dist = 70 + Math.random() * 45
    const side = (Math.random() - 0.5) * 60
    const x = this.player.x + Math.cos(this.yaw) * dist - Math.sin(this.yaw) * side
    const z = this.player.z + Math.sin(this.yaw) * dist + Math.cos(this.yaw) * side
    const y = 32 + Math.random() * 16
    this.effects.push(
      new FireworkShell(this.scene, this.fireworks, {
        from: new THREE.Vector3(x, 2.5, z),
        to: new THREE.Vector3(x, y, z),
        kind,
        color,
        radius: 20 + Math.random() * 10,
        life: 2.6 + Math.random() * 0.8,
        count: 480 + Math.floor(Math.random() * 220),
        ascent: 0.95 + Math.random() * 0.35,
        flash: 1.1,
        onBurst: () => this.audio.boom(0.35),
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
    if (this.catMode) {
      this.updateCatNearby()
      return
    }
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
      this.cb.onPrompt(best ? this.promptFor(best) : null)
    } else if (best) {
      // State-driven labels can change without moving (cooldown, solved…).
      this.cb.onPrompt(this.promptFor(best))
    }
  }

  /** One label per point, reflecting the current eligibility (PRD §4.2). */
  private promptFor(id: InteractableId): Prompt {
    const it = INTERACTABLES.find((i) => i.id === id)
    const label = it?.label ?? ''
    switch (id) {
      case 'entrance':
        return this.claimed ? { id, label, note: '已经点亮', locked: true } : { id, label }
      case 'riddle':
        if (!this.claimed) return { id, label, note: COPY.riddleLocked, locked: true }
        if (this.riddleSolved) return { id, label, note: '已经解开', locked: true }
        return { id, label }
      case 'quay':
        if (!this.riddleSolved) return { id, label, note: COPY.quayLocked, locked: true }
        if (this.releasing) return { id, label, note: COPY.releaseBusy, locked: true }
        if (this.cooldownSeconds() > 0)
          return { id, label, note: COPY.C14(Math.ceil(this.cooldownSeconds())), locked: true }
        if (this.activeOwnerCount() >= RELEASE.maxActive)
          return { id, label, note: COPY.C13, locked: true }
        return { id, label }
      case 'catMask':
        if (!this.claimed) return { id, label, note: COPY.C16, locked: true }
        if (this.catMode) return { id, label, locked: true }
        return { id, label }
    }
  }

  private updateCatNearby() {
    const cat = this.cat
    if (!cat) {
      this.cb.onPrompt(null)
      return
    }
    if (cat.landed) {
      this.cb.onPrompt({ id: 'catMask', label: '下棚' })
    } else if (cat.tipped) {
      this.cb.onPrompt({ id: 'catMask', label: COPY.C21, note: COPY.C20 })
    } else {
      this.cb.onPrompt({ id: 'catMask', label: COPY.C18, note: COPY.C17 })
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
    this.cat?.dispose(this.scene)
    for (const b of this.blessings) {
      this.scene.remove(b.sprite)
      const mat = b.sprite.material as THREE.SpriteMaterial
      mat.map?.dispose()
      mat.dispose()
    }
    this.blessings = []
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
