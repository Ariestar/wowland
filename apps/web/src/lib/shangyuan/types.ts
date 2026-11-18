export type Phase = 'idle' | 'claimed' | 'riddle' | 'style' | 'blessing' | 'released' | 'show'

export type Prompt = {
  id: string
  label: string
  /** Short line under the prompt. */
  note?: string
}

export type PanelOption = {
  label: string
  note?: string
  disabled?: boolean
  correct?: boolean
}

export type Panel = {
  title: string
  body: string
  options: PanelOption[]
  /** Riddle hint shown after a wrong answer. */
  hint?: string
}

export type SceneHud = {
  phase: Phase
  wicks: number
  riddles: number
  released: number
  style: string
  blessing: string
  showActive: boolean
}

export type SceneCallbacks = {
  onProgress: (loaded: number, total: number) => void
  onReady: () => void
  onPrompt: (prompt: Prompt | null) => void
  onHud: (hud: SceneHud) => void
  onPanel: (panel: Panel | null) => void
  onToast: (text: string) => void
}
