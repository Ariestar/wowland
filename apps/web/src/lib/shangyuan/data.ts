/** Layout and copy for the Shangyuan lantern-night preview (Web). */

export type ModelId =
  | 'model-riverbanks'
  | 'model-water'
  | 'model-paifang'
  | 'model-bridge'
  | 'model-lantern-tower'
  | 'model-shop-01'
  | 'model-shop-02'
  | 'model-shop-03'
  | 'model-shop-04'
  | 'model-shop-05'
  | 'model-shop-06'
  | 'model-stall-riddle'
  | 'model-stall-tea'
  | 'model-lantern-array-s1'
  | 'model-lantern-array-s2'
  | 'model-lantern-array-s3'
  | 'model-lantern-array-s4'
  | 'model-quay'
  | 'model-performance'
  | 'model-boat'
  | 'model-skiff'

export type Placement = {
  id: ModelId
  /** Blender X, Y (north positive), Z (up). */
  pos: [number, number, number]
  /** Blender Z rotation in radians; equals three.js Y rotation. */
  rot: number
}

/**
 * Positions come from artifacts/shangyuan/layout.json (Blender metres).
 * three.js position = (bx, bz, -by).
 */
export const PLACEMENTS: Placement[] = [
  { id: 'model-riverbanks', pos: [90, 0, 0], rot: 0 },
  { id: 'model-water', pos: [90, 0, 0], rot: 0 },
  { id: 'model-paifang', pos: [12, 18, 0.58], rot: 0 },
  { id: 'model-bridge', pos: [90, 0, 0], rot: 0 },
  { id: 'model-lantern-tower', pos: [98, 23, 0.58], rot: 0 },
  { id: 'model-shop-01', pos: [34, 25, 0.58], rot: 0 },
  { id: 'model-shop-02', pos: [48, 25, 0.58], rot: 0 },
  { id: 'model-shop-03', pos: [62, 25, 0.58], rot: 0 },
  { id: 'model-shop-04', pos: [76, 25, 0.58], rot: 0 },
  { id: 'model-shop-05', pos: [114, 25, 0.58], rot: 0 },
  { id: 'model-shop-06', pos: [151, 26, 0.58], rot: 0 },
  { id: 'model-stall-riddle', pos: [67, 13.8, 0.58], rot: 0 },
  { id: 'model-stall-tea', pos: [133, 25, 0.58], rot: 0 },
  { id: 'model-lantern-array-s1', pos: [50, 0, 0], rot: 0 },
  { id: 'model-lantern-array-s2', pos: [72, 0, 0], rot: 0 },
  { id: 'model-lantern-array-s3', pos: [128, 0, 0], rot: 0 },
  { id: 'model-lantern-array-s4', pos: [162, 0, 0], rot: 0 },
  { id: 'model-quay', pos: [125, 8.5, 0], rot: 0 },
  { id: 'model-performance', pos: [140, -21, 0.58], rot: 0 },
  { id: 'model-boat', pos: [55, -4, 0.03], rot: 0 },
  { id: 'model-skiff', pos: [154, 4, 0.03], rot: 0 },
  // South bank: reuse the shop modules mirrored so the river reads as a street on both sides.
  // South-bank shops already face the river at rotation 0 (verified in the bridge-top view).
  { id: 'model-shop-03', pos: [40, -32, 0.58], rot: 0 },
  { id: 'model-shop-05', pos: [68, -32, 0.58], rot: 0 },
  { id: 'model-shop-01', pos: [112, -32, 0.58], rot: 0 },
  { id: 'model-stall-tea', pos: [124, -29, 0.58], rot: 0 },
  { id: 'model-shop-02', pos: [78, -34, 0.58], rot: 0 },
  { id: 'model-shop-04', pos: [104, -34, 0.58], rot: 0 },
  // The south landing has a baked blank wall in model-riverbanks; a stall cluster and a
  // lantern row in front of it turn that wall into a backdrop instead of a black box.
  { id: 'model-lantern-array-s2', pos: [92, 0, 0], rot: 0 },
  { id: 'model-stall-tea', pos: [86, -29.5, 0.58], rot: 0 },
  { id: 'model-stall-riddle', pos: [96, -29.5, 0.58], rot: 0 },
]

/** Blockers in Blender (x, y) with half extents; the walker cannot enter them. */
export const BLOCKERS: { x: number; y: number; hx: number; hy: number }[] = [
  { x: 34, y: 25, hx: 5.3, hy: 4.6 },
  { x: 48, y: 25, hx: 5.8, hy: 4.9 },
  { x: 62, y: 25, hx: 5.5, hy: 4.4 },
  { x: 76, y: 25, hx: 6, hy: 4.9 },
  { x: 114, y: 25, hx: 5.3, hy: 4.6 },
  { x: 151, y: 26, hx: 7.6, hy: 7.6 },
  { x: 98, y: 23, hx: 6.5, hy: 6.5 },
  { x: 67, y: 13.8, hx: 2.7, hy: 1.8 },
  { x: 133, y: 25, hx: 2.5, hy: 2 },
  { x: 140, y: -21, hx: 6, hy: 4.2 },
  { x: 40, y: -32, hx: 5.5, hy: 4.4 },
  { x: 68, y: -32, hx: 5.3, hy: 4.6 },
  { x: 112, y: -32, hx: 5.3, hy: 4.6 },
  { x: 124, y: -29, hx: 2.5, hy: 2 },
  { x: 86, y: -29.5, hx: 2.5, hy: 2 },
  { x: 96, y: -29.5, hx: 2.7, hy: 1.8 },
  { x: 78, y: -34, hx: 5.8, hy: 4.9 },
  { x: 104, y: -34, hx: 6, hy: 4.9 },
]

export type InteractableId = 'entrance' | 'riddle' | 'tower' | 'quay' | 'performance'

/** Blender-space interaction anchors. */
export const INTERACTABLES: {
  id: InteractableId
  pos: [number, number]
  radius: number
  label: string
}[] = [
  { id: 'entrance', pos: [13, 16.2], radius: 6, label: '灯门 · 领一盏花灯' },
  { id: 'riddle', pos: [67, 12.9], radius: 4.5, label: '灯谜摊 · 猜一枚灯谜' },
  { id: 'tower', pos: [96, 16], radius: 6, label: '上元灯楼 · 挑选河灯' },
  { id: 'quay', pos: [125, 12.6], radius: 5, label: '埠头 · 放一盏河灯' },
  { id: 'performance', pos: [140, -13], radius: 8, label: '河对岸 · 观看打铁花' },
]

export const VIEWPOINTS: {
  name: string
  pos: [number, number, number]
  look: [number, number, number]
}[] = [
  { name: '入市', pos: [1, 18, 1.7], look: [60, 18, 3.2] },
  { name: '灯市', pos: [44, 18, 1.7], look: [96, 19.5, 6] },
  { name: '桥顶', pos: [93, 0, 6.4], look: [150, 10, 3] },
  { name: '埠头', pos: [121, 8.4, 1.7], look: [100, 22, 6] },
  { name: '对岸', pos: [138, -13, 1.7], look: [98, 20, 8] },
  { name: '远景', pos: [44, 19.2, 9.5], look: [132, 2, 4] },
]

export type Riddle = { question: string; options: string[]; answer: number; hint: string }

export const RIDDLES: Riddle[] = [
  {
    question: '「东风夜放花千树」写的是上元夜的灯。它的下一句是？',
    options: ['更吹落、星如雨', '火树银花合', '月上柳梢头'],
    answer: 0,
    hint: '辛弃疾《青玉案·元夕》：灯火像被东风吹开的千树繁花，又像落下来的星雨。',
  },
  {
    question: '上元节是农历的哪一天？',
    options: ['正月十五', '八月十五', '五月初五'],
    answer: 0,
    hint: '上元即正月十五，是一年里第一个月圆之夜。',
  },
  {
    question: '水上放的河灯，最常做成什么形状？',
    options: ['莲花', '老虎', '石榴'],
    answer: 0,
    hint: '莲花灯浮在水面，灯芯一点，愿望就顺着水走了。',
  },
]

export const LANTERN_STYLES: { name: string; file: string; cost: number; note: string }[] = [
  {
    name: '莲花灯',
    file: 'model-river-lantern-lotus',
    cost: 0,
    note: '最常见的河灯，一朵莲浮在水上',
  },
  {
    name: '纸船灯',
    file: 'model-river-lantern-paperboat',
    cost: 2,
    note: '折一只纸船，把话带到下游',
  },
  { name: '鱼龙灯', file: 'model-river-lantern-fish', cost: 3, note: '鱼龙舞过，灯火也跟着游' },
]

export const BLESSINGS = ['平安顺遂', '阖家团圆', '前程似锦', '与君相逢']
