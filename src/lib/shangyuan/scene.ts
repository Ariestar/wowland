import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js'
import { gradingShader, sanitizeShader } from './postFx'
import { createWaterMaterial, glowTexture } from './water'
import { IronFlower, ParticleBurst, Ripple, type Effect } from './effects'
import {
  BLOCKERS,
  BLESSINGS,
  INTERACTABLES,
  LANTERN_STYLES,
  PLACEMENTS,
  RIDDLES,
  VIEWPOINTS,
  type InteractableId,
} from './data'
import type { Panel, Phase, SceneCallbacks } from './types'
import { ShangyuanAudio } from './audio'

const MODEL_BASE = '/models/shangyuan/'
const EYE = 1.62
const SPEED = 3.6
const RUN = 6.2

/**
 * Bridge deck height in Blender metres. Mirrors `deck_height()` in sy_build.py:
 * 0.72 + 3.05 * (1 - (y / 14.8)^2). Keep these in sync if the arch is rebuilt.
 */
const deckHeight = (y: number) => {
  const t = Math.min(1, Math.abs(y) / 14.8)
  return 0.72 + 3.05 * (1 - t * t)
}

/** True when a Blender (x, y) point is inside a building footprint. */
function blocked(x: number, y: number) {
  for (const b of BLOCKERS) {
    if (Math.abs(x - b.x) < b.hx + 0.35 && Math.abs(y - b.y) < b.hy + 0.35) return true
  }
  return false
}

/** Walkable height at a Blender (x, y) spot; null means water. */
function groundAt(x: number, y: number): number | null {
  if (Math.abs(x - 90) < 2.75 && Math.abs(y) <= 14.7) return deckHeight(y)
  if (Math.abs(y) < 12.4) return null
  if (Math.abs(y) < 15.4) return 0.72
  return 0.65
}

export class ShangyuanScene {
  private readonly canvas: HTMLCanvasElement
  private readonly cb: SceneCallbacks
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private readonly composer: EffectComposer
  private readonly bloom: UnrealBloomPass
  private readonly clock = new THREE.Clock()
  private readonly loader = new GLTFLoader()
  private readonly audio = new ShangyuanAudio()

  private readonly waterMat: THREE.ShaderMaterial
  private readonly glow: THREE.Texture
  private readonly towerGlow: THREE.Sprite[] = []
  private readonly wheelPivots: THREE.Object3D[] = []
  private readonly boats: THREE.Object3D[] = []
  private readonly lanterns: { obj: THREE.Object3D; halo: THREE.Sprite; t: number; speed: number; lane: number }[] = []
  private readonly effects: Effect[] = []
  private readonly lanternTemplates = new Map<string, THREE.Object3D>()

  private player = new THREE.Vector3(1, 0.65 + EYE, -18)
  private yaw = 0
  private pitch = -0.03
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
  private towerPulse = 0
  private nearby: InteractableId | null = null
  private panel: Panel | null = null
  private disposed = false
  private raf = 0
  private photo = false
  private pan: { yaw: number; pitch: number; t: number } | null = null
  private idleClock = 0
  private touchMove = 0
  private touchStrafe = 0

  constructor(canvas: HTMLCanvasElement, callbacks: SceneCallbacks) {
    this.canvas = canvas
    this.cb = callbacks
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
    this.renderer.toneMapping = THREE.NeutralToneMapping
    this.renderer.toneMappingExposure = 1.0
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.info.autoReset = false

    this.camera = new THREE.PerspectiveCamera(62, 1, 0.1, 900)
    this.camera.position.copy(this.player)
    this.scene.fog = new THREE.FogExp2(0x081324, 0.0062)

    this.glow = glowTexture()
    this.waterMat = createWaterMaterial()
    const water = new THREE.Mesh(new THREE.PlaneGeometry(180, 24), this.waterMat)
    water.rotation.x = -Math.PI / 2
    water.position.set(90, 0.05, 0)
    this.scene.add(water)

    this.composer = new EffectComposer(this.renderer)
    this.composer.addPass(new RenderPass(this.scene, this.camera))
    this.composer.addPass(new ShaderPass(sanitizeShader()))
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.3, 0.4, 1.0)
    this.composer.addPass(this.bloom)
    this.composer.addPass(new OutputPass())
    this.composer.addPass(new ShaderPass(gradingShader()))

    this.addSky()
    this.addLights()
    this.bindEvents()
    this.resize()
  }

  // ---------------------------------------------------------------- setup

  private addSky() {
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        uTop: { value: new THREE.Color('#040a18') },
        uMid: { value: new THREE.Color('#0c1c36') },
        uLow: { value: new THREE.Color('#1b2c49') },
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
        uniform vec3 uTop; uniform vec3 uMid; uniform vec3 uLow; uniform vec3 uMoon;
        varying vec3 vDir;
        void main() {
          float h = clamp(vDir.y, -1.0, 1.0);
          vec3 c = mix(uLow, uMid, smoothstep(-0.06, 0.26, h));
          c = mix(c, uTop, smoothstep(0.24, 0.9, h));
          float d = max(dot(vDir, uMoon), 0.0);
          c += vec3(0.9, 0.95, 1.0) * pow(d, 620.0) * 0.8;
          c += vec3(0.22, 0.3, 0.46) * pow(d, 10.0) * 0.3;
          gl_FragColor = vec4(c, 1.0);
        }
      `,
    })
    const sky = new THREE.Mesh(new THREE.SphereGeometry(620, 32, 18), mat)
    sky.frustumCulled = false
    this.scene.add(sky)

    const count = 460
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
      new THREE.PointsMaterial({ size: 1.5, color: 0xdfe8ff, transparent: true, opacity: 0.85, depthWrite: false }),
    )
    stars.frustumCulled = false
    this.scene.add(stars)
  }

  private addLights() {
    this.scene.add(new THREE.AmbientLight(0x2b3f63, 1.3))
    this.scene.add(new THREE.HemisphereLight(0x34527f, 0x090d16, 1.5))

    const moon = new THREE.DirectionalLight(0x9fc0ff, 1.1)
    moon.position.set(-60, 90, 55)
    this.scene.add(moon)

    const warm = (x: number, y: number, z: number, intensity: number, range: number) => {
      const light = new THREE.PointLight(0xffb066, intensity, range, 2)
      light.position.set(x, y, z)
      this.scene.add(light)
    }
    warm(12, 5.2, -18, 20, 22)
    warm(58, 4.5, -21, 16, 20)
    warm(67, 4, -12, 18, 18)
    warm(96, 12, -20, 30, 32)
    warm(125, 4, -10, 16, 20)
    warm(140, 6, 19, 22, 30)
    // South bank: the far facades need their own light or they read as black boxes.
    warm(40, 4.2, 30.6, 26, 18)
    warm(68, 4.2, 30.6, 26, 18)
    warm(112, 4.2, 30.6, 26, 18)
    warm(124, 3.6, 27.6, 16, 14)
    // The baked plaster wall on the south bank needs light in front of it.
    warm(70, 5, 31, 34, 24)
    warm(86, 3.6, 29.2, 24, 16)
    warm(96, 3.4, 29.2, 18, 14)
    warm(140, 4.6, 17, 34, 28)
    warm(147, 3.2, 20, 14, 18)
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
    this.yaw += dx
    this.pitch = Math.max(-1.15, Math.min(1.05, this.pitch - dy))
  }

  private onKeyDown = (e: KeyboardEvent) => {
    if (e.code === 'KeyE') {
      this.interact()
      return
    }
    if (e.code === 'Escape') {
      this.closePanel()
      return
    }
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ShiftLeft', 'ShiftRight'].includes(e.code)) e.preventDefault()
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
  }

  // ---------------------------------------------------------------- loading

  async load() {
    const total = PLACEMENTS.length + 3
    let done = 0
    const tick = () => {
      done++
      this.cb.onProgress(done, total)
    }

    const jobs = PLACEMENTS.map(async (p) => {
      const gltf = await this.loader.loadAsync(`${MODEL_BASE}${p.id}.glb`)
      const root = gltf.scene
      root.position.set(p.pos[0], p.pos[2], -p.pos[1])
      root.rotation.y = p.rot
      root.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const m of mats) {
          const std = m as THREE.MeshStandardMaterial
          if (std.name === 'SY_Lantern') std.emissiveIntensity = 1.35
          if (std.name === 'SY_Paper') std.emissiveIntensity = 1.0
          if (std.name === 'SY_Reflection') {
            std.transparent = true
            std.opacity = 0.5
            std.depthWrite = false
          }
        }
      })
      if (p.id === 'model-lantern-tower') this.prepareTower(root)
      if (p.id === 'model-water') {
        tick()
        return
      }
      if (p.id === 'model-boat' || p.id === 'model-skiff') this.boats.push(root)
      this.scene.add(root)
      tick()
    })

    const templates = ['model-river-lantern-lotus', 'model-river-lantern-paperboat', 'model-river-lantern-fish']
    const templateJobs = templates.map(async (id) => {
      const gltf = await this.loader.loadAsync(`${MODEL_BASE}${id}.glb`)
      gltf.scene.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (!mesh.isMesh) return
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const m of mats) {
          const std = m as THREE.MeshStandardMaterial
          if (std.name === 'SY_Lantern') std.emissiveIntensity = 1.8
          if (std.name === 'SY_Paper') std.emissiveIntensity = 1.5
        }
      })
      this.lanternTemplates.set(id, gltf.scene)
      tick()
    })

    await Promise.all([...jobs, ...templateJobs])
    this.addGroundGlow()
    this.seedAmbientLanterns()
    this.pushHud()
    this.cb.onReady()
    this.loop()
  }

  private prepareTower(root: THREE.Object3D) {
    root.traverse((o) => {
      if (o.name.startsWith('pivot-lantern-wheel')) this.wheelPivots.push(o)
    })
    for (const y of [4.6, 8.2, 11.8, 15.2]) {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: this.glow,
          color: 0xffc98a,
          transparent: true,
          opacity: 0.16,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      )
      sprite.position.set(98, y, -23)
      sprite.scale.setScalar(5.2)
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
      opacity: 0.16,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const pools: [number, number, number, number][] = []
    for (let x = 14; x < 172; x += 11) {
      pools.push([x, 19.2, 8, 0.2])
      pools.push([x + 5, 23.4, 7, 0.13])
      if (x > 30) pools.push([x, -19.2, 8, 0.13])
    }
    pools.push([140, -19.6, 13, 0.34])
    pools.push([124, -22, 8, 0.16])
    for (const [x, y, size, opacity] of pools) {
      const mesh = new THREE.Mesh(geo, mat.clone())
      ;(mesh.material as THREE.MeshBasicMaterial).opacity = opacity
      mesh.rotation.x = -Math.PI / 2
      mesh.position.set(x, 0.68, -y)
      mesh.scale.set(size, size, 1)
      this.scene.add(mesh)
    }
  }

  private seedAmbientLanterns() {
    for (let i = 0; i < 22; i++) {
      const style = i % 4 === 0 ? 'model-river-lantern-paperboat' : 'model-river-lantern-lotus'
      this.spawnLantern(style, 16 + i * 7.4, -8.4 + ((i * 5) % 9), 0.4 + (i % 4) * 0.1)
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
    this.spawnLantern(id, 123.5 + Math.random() * 3, -7.4, 0.42 + Math.random() * 0.16, true)
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
    this.player.set(v.pos[0], v.pos[2], -v.pos[1])
    const dx = v.look[0] - v.pos[0]
    const dz = -(v.look[1] - v.pos[1])
    const dy = v.look[2] - v.pos[2]
    this.yaw = Math.atan2(dz, dx)
    this.pitch = Math.atan2(dy, Math.hypot(dx, dz))
    this.camera.position.copy(this.player)
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
    return ray.intersectObjects(meshes, false).slice(0, 3).map((h) => ({ name: h.object.name, d: +h.distance.toFixed(1) }))
  }

  /** Debug helper: current position in Blender coordinates. */
  where() {
    return { x: +this.player.x.toFixed(1), y: +(-this.player.z).toFixed(1), z: +this.player.y.toFixed(2) }
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
    const g = groundAt(x, y) ?? 0.65
    this.player.set(x, g + EYE, -y)
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
    this.renderer.info.reset()
    this.composer.render()
  }

  private update(dt: number, eventDt = dt) {
    this.move(dt)
    this.updatePan(dt)
    this.camera.position.copy(this.player)
    const dir = new THREE.Vector3(
      Math.cos(this.pitch) * Math.cos(this.yaw),
      Math.sin(this.pitch),
      Math.cos(this.pitch) * Math.sin(this.yaw),
    )
    this.camera.lookAt(this.player.clone().add(dir))

    this.waterMat.uniforms.uTime.value += dt

    for (const wheel of this.wheelPivots) wheel.rotation.z += dt * 0.24
    for (const boat of this.boats) boat.position.y = Math.sin(performance.now() * 0.0005 + boat.position.x) * 0.045

    this.updateLanterns(dt)
    this.updateShow(eventDt)
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
    const step = speed * dt
    const dx = ((f * fx + r * rx) / len) * step
    const dz = ((f * fz + r * rz) / len) * step

    // Try the full step, then each axis on its own, so walls and the bridge edge
    // let the player slide along them instead of stopping dead.
    const attempts: [number, number][] = [
      [dx, dz],
      [dx, 0],
      [0, dz],
    ]
    for (const [ax, az] of attempts) {
      if (!ax && !az) continue
      const nx = this.player.x + ax
      const nz = this.player.z + az
      if (blocked(nx, -nz)) continue
      const g = groundAt(nx, -nz)
      if (g === null) continue
      this.player.x = nx
      this.player.z = nz
      this.player.y = g + EYE
      return
    }
  }

  private updateLanterns(dt: number) {
    const xs = this.waterMat.uniforms.uLanternX.value as Float32Array
    const is = this.waterMat.uniforms.uLanternI.value as Float32Array
    xs.fill(0)
    is.fill(0)
    for (let i = 0; i < this.lanterns.length; i++) {
      const l = this.lanterns[i]
      l.t += dt
      l.obj.position.x += l.speed * dt
      l.obj.position.z = l.lane + Math.sin(l.t * 0.7) * 0.55
      l.obj.position.y = 0.08 + Math.sin(l.t * 1.6) * 0.03
      l.obj.rotation.y = Math.sin(l.t * 0.4) * 0.3
      l.halo.position.set(l.obj.position.x, 0.5, l.obj.position.z)
      if (i < 12) {
        xs[i] = l.obj.position.x
        is[i] = 0.8 + 0.2 * Math.sin(l.t * 2)
      }
      if (l.obj.position.x > 202) {
        l.obj.position.x = 12
        l.t = Math.random() * 6
      }
    }
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
      this.panTo(new THREE.Vector3(140, 5, 20), 1.8)
      for (let i = 0; i < 14; i++) {
        this.spawnLantern(i % 3 === 0 ? 'model-river-lantern-fish' : 'model-river-lantern-lotus', 24 + i * 10, -9 + (i % 5) * 4.2, 0.3 + (i % 3) * 0.12)
      }
      this.pushHud()
    }
    if (t > 1.2 && this.showStage === 1) {
      this.showStage = 2
      this.audio.boom(0.85)
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(140, 4.6, 20)))
      this.pushHud()
    }
    if (t > 2.6 && this.showStage === 2) {
      this.showStage = 3
      this.effects.push(new ParticleBurst(this.scene, this.glow, new THREE.Vector3(140, 15, 24), { count: 620, color: 0xffc07a, spread: 2, speed: 18, size: 0.3, life: 3.2, gravity: 4 }))
      this.audio.boom(0.5)
      this.pushHud()
    }
    if (t > 5.0 && this.showStage === 3) {
      this.showStage = 4
      this.effects.push(new ParticleBurst(this.scene, this.glow, new THREE.Vector3(130, 14, 26), { count: 560, color: 0xff8f60, spread: 2, speed: 16, size: 0.32, life: 3.2, gravity: 4 }))
      this.effects.push(new ParticleBurst(this.scene, this.glow, new THREE.Vector3(152, 14, 24), { count: 480, color: 0xffdfae, spread: 2, speed: 15, size: 0.28, life: 3.2, gravity: 4 }))
      this.audio.boom(0.7)
      this.pushHud()
    }
    if (t > 7.4 && this.showStage === 4) {
      this.showStage = 5
      this.cb.onToast('灯会到了最亮的时候')
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(147, 5, 22)))
      this.pushHud()
    }
    if (t > 11.5 && this.showStage === 5) {
      this.showStage = 6
      this.effects.push(new ParticleBurst(this.scene, this.glow, new THREE.Vector3(138, 17, 27), { count: 700, color: 0xffd8a8, spread: 2, speed: 19, size: 0.3, life: 3.6, gravity: 3.6 }))
      this.effects.push(new ParticleBurst(this.scene, this.glow, new THREE.Vector3(150, 13, 23), { count: 620, color: 0xff9a5a, spread: 2, speed: 17, size: 0.32, life: 3.4, gravity: 3.8 }))
      this.audio.boom(0.6)
      this.pushHud()
    }
    if (t > 16 && this.showStage === 6) {
      this.showStage = 7
      this.effects.push(new IronFlower(this.scene, this.glow, new THREE.Vector3(132, 4.8, 19)))
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
    this.effects.forEach((e) => e.dispose(this.scene))
    this.audio.dispose()
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (mesh.isMesh) {
        mesh.geometry?.dispose()
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        mats.forEach((m) => m?.dispose())
      }
    })
    this.composer.dispose()
    this.renderer.dispose()
  }
}
