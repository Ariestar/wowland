/**
 * Runtime side of the exported collision layout.
 *
 * The Blender scene owns the level: `layout.json` contains the actual walkable
 * triangles (quays, steps, plaza, curved bridge deck) and one solid footprint
 * per blocker.  This module only samples that data.  Keeping the geometry in
 * the level source means a moved stall or a wider promenade can never drift
 * away from the collision box again.
 */

export type CollisionObstacle = {
  name: string
  kind: string
  x: number
  y: number
  hx: number
  hy: number
  top: number
  rot: number
}

export type CollisionLayout = {
  version: number
  units: string
  axes: string
  groundZ: number
  /** Half the canal width in metres; the water shader and lantern drift use it. */
  riverHalf: number
  quayInner: number
  quayOuter: number
  bridge: { y: number; halfSpan: number }
  spawn: { x: number; y: number }
  bounds: {
    minX: number
    maxX: number
    minY: number
    maxY: number
    minZ: number
    maxZ: number
  }
  /** Flat triangle soup in Blender coordinates: x, y, z, x, y, z, ... */
  walkable: number[]
  obstacles: CollisionObstacle[]
}

const CELL = 4

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max))
}

/**
 * A triangle-soup ground field with a coarse spatial hash.  `heightAt` returns
 * the highest surface the player can step onto from `reference`, which is what
 * makes the curved bridge, stairs and the quay coexist without special cases.
 */
export class WalkableGround {
  private readonly tris: Float32Array
  private readonly cells = new Map<number, number[]>()
  private readonly minX: number
  private readonly minY: number
  private readonly cols: number

  constructor(layout: CollisionLayout) {
    this.tris = new Float32Array(layout.walkable)
    this.minX = layout.bounds.minX
    this.minY = layout.bounds.minY
    this.cols = Math.max(1, Math.ceil((layout.bounds.maxX - this.minX) / CELL) + 1)

    const count = this.tris.length / 9
    for (let i = 0; i < count; i++) {
      const offset = i * 9
      const ax = this.tris[offset]
      const ay = this.tris[offset + 1]
      const bx = this.tris[offset + 3]
      const by = this.tris[offset + 4]
      const cx = this.tris[offset + 6]
      const cy = this.tris[offset + 7]
      const x0 = Math.floor((Math.min(ax, bx, cx) - this.minX) / CELL)
      const x1 = Math.floor((Math.max(ax, bx, cx) - this.minX) / CELL)
      const y0 = Math.floor((Math.min(ay, by, cy) - this.minY) / CELL)
      const y1 = Math.floor((Math.max(ay, by, cy) - this.minY) / CELL)
      for (let gy = y0; gy <= y1; gy++) {
        for (let gx = x0; gx <= x1; gx++) {
          const key = gy * this.cols + gx
          const bucket = this.cells.get(key)
          if (bucket) bucket.push(i)
          else this.cells.set(key, [i])
        }
      }
    }
  }

  heightAt(x: number, y: number, reference: number, maxRise = 0.5, maxDrop = 1.2): number | null {
    const gx = Math.floor((x - this.minX) / CELL)
    const gy = Math.floor((y - this.minY) / CELL)
    const bucket = this.cells.get(gy * this.cols + gx)
    if (!bucket) return null

    let best = Number.NEGATIVE_INFINITY
    for (const index of bucket) {
      const offset = index * 9
      const ax = this.tris[offset]
      const ay = this.tris[offset + 1]
      const az = this.tris[offset + 2]
      const bx = this.tris[offset + 3]
      const by = this.tris[offset + 4]
      const bz = this.tris[offset + 5]
      const cx = this.tris[offset + 6]
      const cy = this.tris[offset + 7]
      const cz = this.tris[offset + 8]

      const denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
      if (Math.abs(denominator) < 1e-8) continue
      const w1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / denominator
      const w2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / denominator
      const w3 = 1 - w1 - w2
      if (w1 < -1e-4 || w2 < -1e-4 || w3 < -1e-4) continue

      const height = w1 * az + w2 * bz + w3 * cz
      if (height > reference + maxRise) continue
      if (height < reference - maxDrop) continue
      if (height > best) best = height
    }
    return best === Number.NEGATIVE_INFINITY ? null : best
  }
}

/** Circle vs oriented-box field.  Resolves penetration so the player slides. */
export class ObstacleField {
  private readonly obstacles: CollisionObstacle[]

  constructor(obstacles: CollisionObstacle[]) {
    // Only solid things near the walkable height belong here.  Hanging lanterns,
    // wires and roof overhangs are visual and must not stop a person.
    this.obstacles = obstacles.filter((obstacle) => obstacle.top > 1.6)
  }

  resolveCircle(x: number, y: number, radius: number, feet: number) {
    let px = x
    let py = y
    let hit = false
    for (let pass = 0; pass < 3; pass++) {
      let moved = false
      for (const obstacle of this.obstacles) {
        if (feet >= obstacle.top - 0.05) continue
        const dx = px - obstacle.x
        const dy = py - obstacle.y
        const cos = Math.cos(obstacle.rot)
        const sin = Math.sin(obstacle.rot)
        const lx = dx * cos + dy * sin
        const ly = -dx * sin + dy * cos
        const nearestX = clamp(lx, -obstacle.hx, obstacle.hx)
        const nearestY = clamp(ly, -obstacle.hy, obstacle.hy)
        let ox = lx - nearestX
        let oy = ly - nearestY
        const distance = Math.hypot(ox, oy)
        let push = 0
        if (distance > 1e-6) {
          if (distance >= radius) continue
          push = radius - distance
          ox /= distance
          oy /= distance
        } else {
          // Centre is inside the box: leave through the nearest face.
          const toSide = obstacle.hx - Math.abs(lx)
          const toFront = obstacle.hy - Math.abs(ly)
          if (toSide < toFront) {
            ox = lx >= 0 ? 1 : -1
            oy = 0
            push = toSide + radius
          } else {
            ox = 0
            oy = ly >= 0 ? 1 : -1
            push = toFront + radius
          }
        }
        px += (ox * cos - oy * sin) * push
        py += (ox * sin + oy * cos) * push
        hit = true
        moved = true
      }
      if (!moved) break
    }
    return { x: px, y: py, hit }
  }
}
