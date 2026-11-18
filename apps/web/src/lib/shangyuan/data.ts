/** Layout and copy for the Shangyuan lantern-night preview (Web). */

/**
 * Runtime constants that are not authored in Blender.  Ground height, river
 * width, quay extents and the bridge profile now come from `layout.json`, so
 * they have one source instead of a duplicated table here.
 */
export const SCENE = {
  groundZ: 1.2,
} as const

export type InteractableId = 'entrance' | 'riddle' | 'tower' | 'quay' | 'performance'

/** Blender-space interaction anchors. */
export const INTERACTABLES: {
  id: InteractableId
  pos: [number, number]
  radius: number
  label: string
}[] = [
  { id: 'entrance', pos: [16.4, -120], radius: 7, label: '灯门 · 领一盏花灯' },
  { id: 'riddle', pos: [15.6, 40], radius: 4.5, label: '灯谜摊 · 猜一枚灯谜' },
  { id: 'tower', pos: [16.4, 78], radius: 6, label: '上元灯楼 · 挑选河灯' },
  { id: 'quay', pos: [13.4, 118], radius: 3.4, label: '埠头 · 放一盏河灯' },
  { id: 'performance', pos: [-16.2, 26], radius: 7, label: '河对岸 · 观看打铁花' },
]

export const VIEWPOINTS: {
  name: string
  pos: [number, number, number]
  look: [number, number, number]
}[] = [
  { name: '入市', pos: [16.4, -132, 2.82], look: [0, 30, 8] },
  { name: '灯市', pos: [16.4, -56, 2.82], look: [0, 20, 8] },
  { name: '桥顶', pos: [0, 10, 9.2], look: [0, 78, 14] },
  { name: '埠头', pos: [13.6, 118, 2.82], look: [-16, 108, 4] },
  { name: '对岸', pos: [-16.4, 40, 2.82], look: [16.4, 55, 6] },
  { name: '远景', pos: [16.4, -152, 7.2], look: [0, 70, 12] },
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
