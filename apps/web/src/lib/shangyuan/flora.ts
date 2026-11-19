import * as THREE from 'three'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'

/**
 * Procedural waterline planting.
 *
 * The quay is a straight stone edge for three hundred metres, so the eye has
 * nothing to read where the bank meets the water.  Reed blades and cattails
 * put a broken, wind-moved silhouette against the reflection.  Both are
 * generated here instead of in Blender because the value is in the per-blade
 * variation and the sway; a single reusable mesh would look stamped.
 *
 * One draw call per mesh, roughly 10k triangles in total.
 */
export class WaterlineFlora {
  readonly object = new THREE.Group()
  private readonly reeds: THREE.InstancedMesh
  private readonly cattails: THREE.InstancedMesh
  private readonly time = { value: 0 }
  private readonly materials: THREE.Material[] = []

  constructor(bankX: number, waterY: number) {
    const rng = mulberry32(20261119)
    const reedCount = 1680
    const cattailCount = 64

    const blade = bladeGeometry()
    const reedMat = windMaterial(this.time, 'waterline-reed')
    this.materials.push(reedMat)
    this.reeds = new THREE.InstancedMesh(blade, reedMat, reedCount)
    this.reeds.instanceMatrix.setUsage(THREE.StaticDrawUsage)

    const stalk = cattailGeometry()
    const cattailMat = windMaterial(this.time, 'waterline-cattail')
    this.materials.push(cattailMat)
    this.cattails = new THREE.InstancedMesh(stalk, cattailMat, cattailCount)
    this.cattails.instanceMatrix.setUsage(THREE.StaticDrawUsage)

    const matrix = new THREE.Matrix4()
    const position = new THREE.Vector3()
    const scale = new THREE.Vector3()
    const quaternion = new THREE.Quaternion()
    const euler = new THREE.Euler()
    const tint = new THREE.Color()
    const palette = ['#e9e3c6', '#cfd8ab', '#f1e7c2', '#ded4ac', '#c2cba0'].map(
      (hex) => new THREE.Color(hex),
    )

    // Even spacing per bank guarantees the whole canal is planted; the jitter
    // and per-stand blade count keep it from reading as a hedge.  The bridge
    // span and the ferry steps stay clear.
    const stands: { x: number; z: number }[] = []
    for (let side = -1; side <= 1; side += 2) {
      const count = 78
      for (let i = 0; i < count; i++) {
        const z = -152 + ((i + 0.5) / count) * 338 + (rng() - 0.5) * 3.4
        if (z > -4 && z < 26) continue
        if (side === 1 && z > 105 && z < 131) continue
        stands.push({ x: side * (bankX - 0.28 - rng() * 0.9), z })
      }
    }

    let bladeIndex = 0
    let cattailIndex = 0
    for (const stand of stands) {
      const blades = 6 + Math.floor(rng() * 9)
      for (let b = 0; b < blades && bladeIndex < reedCount; b++) {
        const h = 0.95 + rng() * 1.45
        position.set(stand.x + (rng() - 0.5) * 0.55, waterY - 0.14, stand.z + (rng() - 0.5) * 1.6)
        euler.set((rng() - 0.5) * 0.2, rng() * Math.PI * 2, (rng() - 0.5) * 0.2)
        quaternion.setFromEuler(euler)
        scale.set(0.75 + rng() * 0.55, h, 0.75 + rng() * 0.55)
        matrix.compose(position, quaternion, scale)
        this.reeds.setMatrixAt(bladeIndex, matrix)
        tint.copy(palette[Math.floor(rng() * palette.length)])
        this.reeds.setColorAt(bladeIndex, tint)
        bladeIndex += 1
      }
      // One cattail head per few stands; a full row of them would read as a
      // crop rather than a river edge.
      if (cattailIndex < cattailCount && rng() < 0.4) {
        const h = 1.05 + rng() * 0.5
        position.set(stand.x + (rng() - 0.5) * 0.5, waterY - 0.12, stand.z + (rng() - 0.5) * 1.4)
        euler.set((rng() - 0.5) * 0.14, rng() * Math.PI * 2, (rng() - 0.5) * 0.14)
        quaternion.setFromEuler(euler)
        scale.set(0.9 + rng() * 0.35, h, 0.9 + rng() * 0.35)
        matrix.compose(position, quaternion, scale)
        this.cattails.setMatrixAt(cattailIndex, matrix)
        tint.setHSL(0.11 + rng() * 0.03, 0.24, 0.42 + rng() * 0.12)
        this.cattails.setColorAt(cattailIndex, tint)
        cattailIndex += 1
      }
    }
    // Fill any unused slots far below the river so a short random walk never
    // leaves an instance sitting at the origin.
    const hidden = new THREE.Matrix4().makeTranslation(0, -50, 0)
    for (; bladeIndex < reedCount; bladeIndex++) this.reeds.setMatrixAt(bladeIndex, hidden)
    for (; cattailIndex < cattailCount; cattailIndex++) {
      this.cattails.setMatrixAt(cattailIndex, hidden)
    }
    this.reeds.instanceMatrix.needsUpdate = true
    this.cattails.instanceMatrix.needsUpdate = true
    if (this.reeds.instanceColor) this.reeds.instanceColor.needsUpdate = true
    if (this.cattails.instanceColor) this.cattails.instanceColor.needsUpdate = true

    this.object.add(this.reeds, this.cattails)
  }

  update(dt: number) {
    // The sway lives in the vertex shader; the CPU only advances its clock.
    this.time.value += dt
  }

  dispose() {
    this.object.removeFromParent()
    this.reeds.geometry.dispose()
    this.cattails.geometry.dispose()
    this.reeds.dispose()
    this.cattails.dispose()
    for (const material of this.materials) material.dispose()
  }
}

/** A tapered blade, five rows so the bend reads as a curve rather than a tilt. */
function bladeGeometry() {
  const rows = 5
  const positions: number[] = []
  const colors: number[] = []
  const indices: number[] = []
  const base = new THREE.Color('#6b7548')
  const tip = new THREE.Color('#e0d49c')
  const c = new THREE.Color()
  for (let r = 0; r < rows; r++) {
    const t = r / (rows - 1)
    const half = 0.038 * (1 - 0.86 * t) + 0.0035
    const z = t * t * 0.16
    c.copy(base).lerp(tip, t * t)
    positions.push(-half, t, z, half, t, z)
    colors.push(c.r, c.g, c.b, c.r, c.g, c.b)
  }
  for (let r = 0; r < rows - 1; r++) {
    const a = r * 2
    indices.push(a, a + 2, a + 1, a + 1, a + 2, a + 3)
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  geo.setIndex(indices)
  geo.computeVertexNormals()
  return geo
}

/** Thin stalk with a brown seed head, merged so it stays one instanced draw. */
function cattailGeometry() {
  const stalk = new THREE.CylinderGeometry(0.012, 0.021, 0.94, 4, 1, true)
  stalk.translate(0, 0.47, 0)
  paint(stalk, '#4c5832')
  const head = new THREE.CylinderGeometry(0.034, 0.05, 0.27, 6, 1)
  head.translate(0, 1.0, 0)
  paint(head, '#7a5230')
  return mergeGeometries([stalk, head]) ?? stalk
}

function paint(geometry: THREE.BufferGeometry, hex: string) {
  const c = new THREE.Color(hex)
  const count = geometry.getAttribute('position').count
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    colors[i * 3] = c.r
    colors[i * 3 + 1] = c.g
    colors[i * 3 + 2] = c.b
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
}

/**
 * Standard lighting plus a vertex-shader bend.  The blade's local Y is the
 * height fraction, so the tip travels and the root stays planted; the instance
 * origin seeds the phase so neighbours do not sway in lockstep.
 */
function windMaterial(time: { value: number }, cacheKey: string) {
  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.86,
    metalness: 0,
    side: THREE.DoubleSide,
    // The bank lights sit four metres up; without a floor the shaded side of
    // every blade collapses into the dark water behind it.
    emissive: new THREE.Color('#171b0e'),
    emissiveIntensity: 1,
  })
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uSwayTime = time
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uSwayTime;')
      .replace(
        '#include <begin_vertex>',
        /* glsl */ `#include <begin_vertex>
        #ifdef USE_INSTANCING
          vec3 swayOrigin = instanceMatrix[3].xyz;
        #else
          vec3 swayOrigin = vec3(0.0);
        #endif
        float swayPhase = swayOrigin.x * 0.63 + swayOrigin.z * 0.41;
        float swayBend = pow(max(transformed.y, 0.0), 1.5);
        float sway =
          sin(uSwayTime * 1.05 + swayPhase) * 0.085 +
          sin(uSwayTime * 2.6 + swayPhase * 1.9) * 0.028;
        transformed.x += sway * swayBend;
        transformed.z += sway * 0.55 * swayBend;
      `,
      )
  }
  material.customProgramCacheKey = () => cacheKey
  return material
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
