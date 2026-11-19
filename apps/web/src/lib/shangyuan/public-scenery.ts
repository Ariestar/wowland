import * as THREE from 'three'
import type { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

const BASE = '/models/lantern-river/library/'

type Spot = {
  x: number
  y: number
  z: number
  yaw: number
  sx: number
  sy: number
  sz: number
}

type Part = {
  geometry: THREE.BufferGeometry
  material: THREE.Material
}

export type PublicSceneryStats = {
  sakura: number
  willow: number
  bamboo: number
  pavilions: number
  corridors: number
}

/**
 * The level data and the official viewpoints use Blender coordinates: x is
 * lateral, negative y runs into the scene, z is height.  The Web scene uses
 * x/height/-y, so convert once here instead of hand-flipping every placement.
 */
function sceneSpot(
  blenderX: number,
  blenderY: number,
  scale: number,
  yaw = 0,
  height = 1.2,
  squash = 1,
): Spot {
  return {
    x: blenderX,
    y: height,
    z: -blenderY,
    yaw,
    sx: scale,
    sy: scale * squash,
    sz: scale,
  }
}

/** Official editor-library models placed through instanced batches where repeated. */
export class PublicScenery {
  readonly object = new THREE.Group()

  private readonly counts: PublicSceneryStats = {
    sakura: 0,
    willow: 0,
    bamboo: 0,
    pavilions: 0,
    corridors: 0,
  }

  constructor(
    private readonly loader: GLTFLoader,
    private readonly renderer: THREE.WebGLRenderer,
  ) {
    this.object.name = 'AwcPublicScenery'
  }

  async load() {
    await Promise.all([
      this.loadPlants(
        'sakura-tree.glb',
        [
          sceneSpot(-17.7, -126, 5.2, 0.25),
          sceneSpot(17.7, -112, 5.0, -0.3),
          sceneSpot(-17.7, -120, 5.4, 0.5),
          sceneSpot(-17.8, -88, 5.2, -0.2),
        ],
        'sakura',
      ),
      this.loadPlants(
        'willow.glb',
        [
          sceneSpot(13.5, -124, 4.2, 0.1, 1.2, 1.1),
          sceneSpot(14.9, -108, 5.0, -0.2, 1.2, 1.1),
          sceneSpot(-14.9, -108, 5.3, 0.3, 1.2, 1.1),
        ],
        'willow',
      ),
      this.loadPlants(
        'bamboo.glb',
        [
          sceneSpot(13.2, -126.5, 2.7, 0.1),
          sceneSpot(13.8, -125.2, 3.1, -0.2),
          sceneSpot(13.1, -123.9, 2.6, 0.3),
          sceneSpot(14.1, -122.6, 2.9, -0.1),
          sceneSpot(13.4, -121.3, 2.5, 0.25),
          sceneSpot(13.2, -88.5, 2.8, -0.3),
          sceneSpot(13.9, -87.2, 2.6, 0.15),
          sceneSpot(13.3, -85.9, 3.0, -0.2),
        ],
        'bamboo',
      ),
      this.loadStructureBatch(
        'wood-pavilion.glb',
        [sceneSpot(10.8, -101.5, 5.6, -0.12)],
        'pavilions',
      ),
      this.loadStructureBatch(
        'crossing-corridor.glb',
        [sceneSpot(-9, -110.5, 9.2), sceneSpot(0, -110.5, 9.2), sceneSpot(9, -110.5, 9.2)],
        'corridors',
      ),
    ])
    this.addPavilionTerrace()
  }

  stats(): PublicSceneryStats {
    return { ...this.counts }
  }

  dispose() {
    const geometries = new Set<THREE.BufferGeometry>()
    const materials = new Set<THREE.Material>()
    const textures = new Set<THREE.Texture>()
    this.object.traverse((object) => {
      const mesh = object as THREE.Mesh
      if (!mesh.isMesh) return
      geometries.add(mesh.geometry)
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      for (const material of mats) {
        materials.add(material)
        const std = material as THREE.MeshStandardMaterial
        for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap'] as const) {
          if (std[key]) textures.add(std[key])
        }
      }
    })
    for (const texture of textures) texture.dispose()
    for (const material of materials) material.dispose()
    for (const geometry of geometries) geometry.dispose()
  }

  private tune(material: THREE.Material, anisotropy: number) {
    const std = material as THREE.MeshStandardMaterial
    std.envMapIntensity = 0.9
    std.dithering = true
    for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap'] as const) {
      const texture = std[key]
      if (!texture) continue
      texture.anisotropy = anisotropy
      texture.needsUpdate = true
    }
  }

  private collectParts(source: THREE.Object3D, anisotropy: number): Part[] {
    const parts: Part[] = []
    source.updateMatrixWorld(true)
    source.traverse((object) => {
      const mesh = object as THREE.Mesh
      if (!mesh.isMesh) return
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      for (const material of materials) this.tune(material, anisotropy)
      const geometry = mesh.geometry.clone().applyMatrix4(mesh.matrixWorld)
      const index = geometry.getIndex()
      if (geometry.groups.length > 1 && index) {
        for (const group of geometry.groups) {
          const part = geometry.clone()
          const indices: number[] = []
          for (let i = group.start; i < group.start + group.count; i++) {
            indices.push(index.getX(i))
          }
          part.setIndex(indices)
          part.clearGroups()
          parts.push({
            geometry: part,
            material: materials[group.materialIndex ?? 0] ?? materials[0],
          })
        }
        geometry.dispose()
      } else {
        parts.push({ geometry, material: materials[0] })
      }
    })
    source.traverse((object) => {
      const mesh = object as THREE.Mesh
      if (mesh.isMesh) mesh.geometry.dispose()
    })
    return parts
  }

  private addInstances(file: string, spots: Spot[], name: string) {
    const gltf = this.loader.loadAsync(file.startsWith('/') ? file : `${BASE}${file}`)
    return gltf.then((loaded) => {
      const anisotropy = this.renderer.capabilities.getMaxAnisotropy()
      const parts = this.collectParts(loaded.scene, anisotropy)
      const matrix = new THREE.Matrix4()
      const position = new THREE.Vector3()
      const quaternion = new THREE.Quaternion()
      const scale = new THREE.Vector3()
      for (const part of parts) {
        const batch = new THREE.InstancedMesh(part.geometry, part.material, spots.length)
        batch.name = name
        batch.castShadow = true
        batch.receiveShadow = true
        spots.forEach((item, index) => {
          position.set(item.x, item.y, item.z)
          quaternion.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, item.yaw)
          scale.set(item.sx, item.sy, item.sz)
          matrix.compose(position, quaternion, scale)
          batch.setMatrixAt(index, matrix)
        })
        batch.instanceMatrix.needsUpdate = true
        batch.computeBoundingSphere()
        this.object.add(batch)
      }
    })
  }

  private loadPlants(file: string, spots: Spot[], key: 'sakura' | 'willow' | 'bamboo') {
    return this.addInstances(file, spots, `AwcScenery_${key}`).then(() => {
      this.counts[key] = spots.length
    })
  }

  private loadStructureBatch(file: string, spots: Spot[], key: 'pavilions' | 'corridors') {
    return this.addInstances(file, spots, `AwcScenery_${key}`).then(() => {
      this.counts[key] += spots.length
    })
  }

  /** Stone terrace that carries the waterside pavilion over the quay edge. */
  private addPavilionTerrace() {
    const terrace = new THREE.Mesh(
      new THREE.BoxGeometry(6.4, 0.52, 6.2),
      new THREE.MeshStandardMaterial({
        color: 0x68534d,
        roughness: 0.92,
        metalness: 0.02,
        dithering: true,
      }),
    )
    terrace.name = 'AwcScenery_PavilionTerrace'
    terrace.position.set(10.8, 0.94, 101.5)
    terrace.castShadow = true
    terrace.receiveShadow = true
    this.object.add(terrace)
  }
}
