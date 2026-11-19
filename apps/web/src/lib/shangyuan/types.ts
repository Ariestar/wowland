/**
 * MVP state model (PRD §9.1).
 *
 * The main line is a strict sequence: unclaimed → claimed → riddle solved →
 * first release.  Show, photo and cat states are independent and never reset
 * confirmed main-line progress.
 */
export type Phase = 'idle' | 'claimed' | 'riddle' | 'released' | 'show'

export type Prompt = {
  id: string
  label: string
  /** Short line under the prompt. */
  note?: string
  /** True when the action is locked by an unmet prerequisite. */
  locked?: boolean
}

export type PanelOption = {
  label: string
  note?: string
  disabled?: boolean
  correct?: boolean
}

export type PanelKind = 'claim' | 'riddle' | 'release' | 'show' | 'info'

export type Panel = {
  kind: PanelKind
  title: string
  body: string
  options: PanelOption[]
  /** Riddle hint shown after a wrong answer. */
  hint?: string
  /** Release-panel draft state, kept server-side so closing preserves it. */
  selectedStyle?: number
  selectedBlessing?: number
  confirmLabel?: string
}

export type SceneHud = {
  phase: Phase
  /** Main-line completion flags (PRD §9.1). */
  claimed: boolean
  riddleSolved: boolean
  released: boolean
  /** Total successful releases this session. */
  releasedCount: number
  /** Active player lanterns on the water. */
  activeLanterns: number
  /** Seconds until the next release is allowed; 0 when ready. */
  cooldown: number
  style: string
  blessing: string
  showActive: boolean
  /** Cat-mode state. */
  cat: CatHud
}

export type CatHud = {
  active: boolean
  /** Basket tipped this attempt. */
  basketTipped: boolean
  /** On the shed this attempt. */
  onShed: boolean
  /** Completed at least once this session. */
  completed: boolean
  /** Current action label for the cat action button. */
  action: string
}

export type SceneCallbacks = {
  onProgress: (loaded: number, total: number) => void
  onReady: () => void
  onPrompt: (prompt: Prompt | null) => void
  onHud: (hud: SceneHud) => void
  onPanel: (panel: Panel | null) => void
  onToast: (text: string) => void
}
