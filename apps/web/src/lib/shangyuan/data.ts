/**
 * Layout and copy for the Shangyuan lantern-night MVP fragment (Web).
 *
 * All positions are Blender coordinates (x, y on the ground plane), matching
 * layout.json.  The runtime converts to game space (z = -y) where needed.
 *
 * The MVP fragment follows the PRD §3.2 short route: one bank, one direction,
 * roughly 40–55 m of walking.  Distances verified against the exported
 * collision (walkable triangles + obstacle footprints).
 */

/** Runtime constants that are not authored in Blender. */
export const SCENE = {
  groundZ: 1.2,
} as const

export const MVP_S1 = {
  model: '/models/mvp/s1-entrance.glb',
  /** Blender-space table centre; Three.js maps it to (x, groundZ, -y). */
  pos: [16.4, -123] as const,
  spawn: [16.4, -128] as const,
  radius: 2.5,
  collider: { hx: 1.05, hy: 0.72, top: 3.1 },
} as const

/** MVP release rules (PRD §7.5). */
export const RELEASE = {
  /** Maximum player lanterns drifting at once. */
  maxActive: 5,
  /** Seconds between two successful releases. */
  cooldown: 10,
  /** Seconds a player lantern drifts before fading out. */
  lifetime: 60,
  /** Seconds the fresh lantern keeps its identification glow. */
  glowTime: 3,
  /** Drift speed range in m/s (PRD §7.5). */
  speedMin: 0.4,
  speedMax: 0.62,
} as const

export type InteractableId = 'entrance' | 'riddle' | 'quay' | 'catMask'

/**
 * Interaction anchors for the MVP fragment.
 * Radii follow PRD §4.2 drafting values (2.5 m general, ~1.5 m release).
 */
export const INTERACTABLES: {
  id: InteractableId
  pos: [number, number]
  radius: number
  label: string
}[] = [
  // P01, open paving north of the paifang, clear of stall_21, the columns and
  // the planter strip (PRD §5.1 keeps the stand beside the gate).
  { id: 'entrance', pos: [MVP_S1.pos[0], MVP_S1.pos[1]], radius: MVP_S1.radius, label: '点亮花灯' },
  // P02, in front of stall_22 (stall face at x ≈ 16.4).
  { id: 'riddle', pos: [15.6, -104], radius: 2.5, label: '猜灯谜' },
  // P04, quay edge level with the release platform; tighter range per PRD.
  // Offset south of the quay post at (12.85, -88) so the post never blocks the
  // release framing.
  { id: 'quay', pos: [13.5, -86.4], radius: 1.6, label: '放河灯' },
  // P06, mask stand beside the riddle stall, ~4.5 m from the riddle point.
  { id: 'catMask', pos: [16.2, -99.5], radius: 2.0, label: '戴上狸奴面具' },
]

/**
 * Viewpoints stay inside the MVP fragment; they are sightseeing shortcuts and
 * never gate main-line progress (PRD §9.4).
 */
export const VIEWPOINTS: {
  name: string
  pos: [number, number, number]
  look: [number, number, number]
}[] = [
  { name: '入市', pos: [16.4, -128, 2.82], look: [16.2, -122, 3.2] },
  { name: '灯谜', pos: [14.2, -97, 2.82], look: [17.5, -104, 3] },
  { name: '埠头', pos: [14.6, -83, 2.82], look: [11.5, -90, 1.5] },
  { name: '灯街', pos: [16.4, -138, 2.82], look: [8, -60, 8] },
]

export type Riddle = { question: string; options: string[]; answer: number; hint: string }

/** One stall, one riddle (PRD §6.2). */
export const RIDDLE: Riddle = {
  question: '红红圆圆挂门前，一到夜里亮闪闪。打一物。',
  options: ['纸船', '花灯', '团扇'],
  answer: 1,
  hint: '再想想，它就挂在眼前的灯架上。',
}

export const LANTERN_STYLES: { name: string; file: string; meaning: string }[] = [
  { name: '莲花灯', file: 'model-river-lantern-lotus', meaning: '平安喜乐' },
  { name: '纸船灯', file: 'model-river-lantern-paperboat', meaning: '一帆风顺' },
  { name: '鱼龙灯', file: 'model-river-lantern-fish', meaning: '年年有余' },
]

export const BLESSINGS = ['平安顺遂', '阖家团圆', '前程似锦', '与君相逢']

/**
 * The G0 cat-play area (PRD §8).  The east-bank street is ~7 m wide, so the
 * prototype zone takes the eastern strip between stall_22 and stall_3 and
 * leaves a ≥3.5 m human passage on the river side.  Bounds are Blender coords:
 * x 16.4–19.6, y -98.2…-92.2.  Verified empty of obstacle footprints.
 */
export const CAT_ZONE = {
  minX: 16.4,
  maxX: 19.6,
  minY: -98.2,
  maxY: -92.2,
  /** P07, where the cat appears and returns. */
  spawn: { x: 17.0, y: -97.4 } as const,
  /** P08, the basket the cat pounces. */
  basket: { x: 18.1, y: -95.4 } as const,
  /** P09, the shed landing 1.2 m up; the paw print marks the jump spot. */
  shed: { x: 19.1, y: -93.1, height: 1.2 } as const,
  pawPrint: { x: 18.5, y: -93.7 } as const,
  /** PRD §8.4 drafting values. */
  walkSpeed: 2.6,
  pounceRange: 1.1,
  jumpRange: 1.6,
} as const

/** Main-line copy from PRD §11.2, keyed by id for traceability. */
export const COPY = {
  C01: '走到灯案前，点亮你的花灯。',
  C02: '点亮花灯',
  C03: '花灯亮了，去灯谜摊换一盏河灯。',
  C04: '先到牌坊点亮花灯。',
  C05: '猜灯谜',
  C06: '再想想，它就挂在眼前的灯架上。',
  C07: '猜中了！去埠头挑一盏河灯吧。',
  C08: '先猜中一道灯谜，再来放灯。',
  C09: '放河灯',
  C10: '放出这盏灯',
  C11: '心愿已入河，继续逛逛吧。',
  C12: '这盏灯暂时没能放出，请再试一次。',
  C13: '河上灯还多，稍等一会再放。',
  C14: (seconds: number) => `再等 ${seconds} 秒，可放下一盏。`,
  C15: '戴上狸奴面具',
  C16: '先点亮花灯，再来戴面具。',
  C17: '走近竹筐，试着扑一下。',
  C18: '扑一下',
  C19: '又是你这小狸奴！',
  C20: '去爪印处，跃上矮棚。',
  C21: '跃上矮棚',
  C22: '淘气成功，摊主够不着你啦。',
  C23: '退出狸奴试玩',
  C24: '位置已恢复，进度保留。',
  C25: '轻触空白处退出，使用系统截图。',
  C26: (action: string) => `先退出狸奴试玩，再来${action}。`,
  claimedAgain: '花灯已经点亮。',
  riddleDone: '这道谜已经解开，去埠头挑一盏河灯吧。',
  riddleLocked: '先到牌坊点亮花灯。',
  quayLocked: '先猜中一道灯谜，再来放灯。',
  releaseBusy: '河灯正在入水，稍等一下。',
  photoWatermark: '桃源·上元灯会',
} as const
