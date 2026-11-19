'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { VIEWPOINTS } from '@/lib/shangyuan/data'
import { ShangyuanScene } from '@/lib/shangyuan/scene'
import type { Panel, Prompt, SceneHud } from '@/lib/shangyuan/types'
import s from './ShangyuanWorld.module.css'

type Props = { language: 'zh' | 'en' }

const COPY = {
  zh: {
    title: '上元灯夜',
    subtitle: '提一盏灯，猜一道谜，把心愿放进一条会发光的河。',
    enter: '进入灯会',
    enterNote: 'WASD 行走 · 鼠标转视角 · E 交互 · Esc 放开鼠标',
    loading: '灯正在一盏盏亮起',
    ready: '灯已点亮',
    step1: '点灯',
    step2: '解谜',
    step3: '放灯',
    done: '✓',
    todo: '○',
    wicks: '灯',
    lanterns: '河上灯',
    cooldown: '可再放',
    style: '手中灯',
    none: '未选',
    viewpoints: '机位',
    photo: '留影',
    exitPhoto: '退出留影',
    mute: '静音',
    unmute: '声音',
    back: '回到领灯点',
    ekey: 'E',
    interact: '交互',
    close: '先不看了',
    hint: '提示',
    mobile: '拖动画面转视角',
    confirm: '放出这盏灯',
    selected: '已选',
    photoHint: '轻触空白处退出，使用系统截图。',
    watermark: '桃源·上元灯会',
    catExit: '退出狸奴试玩',
    catReset: '回到猫垫',
    catStep1: '扑倒竹筐',
    catStep2: '跃上矮棚',
    catDone: '狸奴试玩完成',
  },
  en: {
    title: 'Shangyuan Lantern Night',
    subtitle: 'Carry a lantern, solve one riddle, set a wish on a river of light.',
    enter: 'Enter the night market',
    enterNote: 'WASD to walk · mouse to look · E to interact · Esc to release the cursor',
    loading: 'Lighting the lanterns',
    ready: 'The lanterns are lit',
    step1: 'Light',
    step2: 'Riddle',
    step3: 'Release',
    done: '✓',
    todo: '○',
    wicks: 'Lantern',
    lanterns: 'On river',
    cooldown: 'Ready in',
    style: 'Lantern',
    none: 'none',
    viewpoints: 'Views',
    photo: 'Photo',
    exitPhoto: 'Leave photo',
    mute: 'Mute',
    unmute: 'Sound',
    back: 'To the gate',
    ekey: 'E',
    interact: 'Interact',
    close: 'Not now',
    hint: 'Hint',
    mobile: 'Drag to look around',
    confirm: 'Release this lantern',
    selected: 'Chosen',
    photoHint: 'Tap blank space to leave; use the system screenshot.',
    watermark: 'Shangyuan Lantern Night',
    catExit: 'Leave the cat trial',
    catReset: 'Back to the mat',
    catStep1: 'Tip the basket',
    catStep2: 'Leap to the shed',
    catDone: 'Cat trial complete',
  },
} as const

export default function ShangyuanWorld({ language }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<ShangyuanScene | null>(null)
  const [progress, setProgress] = useState(0)
  const [ready, setReady] = useState(false)
  const [entered, setEntered] = useState(false)
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [panel, setPanel] = useState<Panel | null>(null)
  const [hud, setHud] = useState<SceneHud>({
    phase: 'idle',
    claimed: false,
    riddleSolved: false,
    released: false,
    releasedCount: 0,
    activeLanterns: 0,
    cooldown: 0,
    style: '',
    blessing: '',
    showActive: false,
    cat: { active: false, basketTipped: false, onShed: false, completed: false, action: '' },
  })
  const [toast, setToast] = useState('')
  const [photo, setPhoto] = useState(false)
  const [photoHint, setPhotoHint] = useState(false)
  const [muted, setMuted] = useState(false)
  const [view, setView] = useState(0)
  const toastTimer = useRef<number | null>(null)
  const hintTimer = useRef<number | null>(null)
  const t = COPY[language]

  const flash = useCallback((text: string) => {
    setToast(text)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 3200)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const scene = new ShangyuanScene(canvas, {
      onProgress: (loaded, total) => setProgress(loaded / total),
      onReady: () => setReady(true),
      onPrompt: setPrompt,
      onHud: setHud,
      onPanel: setPanel,
      onToast: flash,
    })
    sceneRef.current = scene
    // Preview-only hook used by scripts/shangyuan/capture.cjs; harmless in production.
    ;(window as unknown as { __shangyuan?: unknown }).__shangyuan = scene
    void scene.load().catch(() => flash('场景加载失败，请刷新重试'))
    return () => {
      scene.dispose()
      sceneRef.current = null
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
      if (hintTimer.current) window.clearTimeout(hintTimer.current)
    }
  }, [flash])

  const togglePhoto = useCallback(() => {
    const next = sceneRef.current?.togglePhoto() ?? false
    setPhoto(next)
    if (next) {
      // PRD §7.6: show the exit hint once for ~3 s, then fade it out.
      setPhotoHint(true)
      setToast('')
      if (hintTimer.current) window.clearTimeout(hintTimer.current)
      hintTimer.current = window.setTimeout(() => setPhotoHint(false), 3000)
    } else {
      setPhotoHint(false)
    }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Escape' && photo) {
        togglePhoto()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [photo, togglePhoto])

  const enter = () => {
    setEntered(true)
    sceneRef.current?.setViewpoint(0)
  }

  const choose = (index: number) => sceneRef.current?.choose(index)

  const toggleMute = () => {
    const next = !muted
    setMuted(next)
    sceneRef.current?.setMuted(next)
  }

  const suggestion = (() => {
    if (hud.cat.active) {
      return hud.cat.completed
        ? '狸奴试玩完成，可以退出继续逛。'
        : hud.cat.onShed
          ? '在棚上歇一会，或退出试玩。'
          : hud.cat.basketTipped
            ? '去爪印处，跃上矮棚。'
            : '走近竹筐，试着扑一下。'
    }
    if (!hud.claimed) return '走到灯案前，点亮你的花灯。'
    if (!hud.riddleSolved) return '到灯谜摊猜一道谜。'
    if (!hud.released) return '去埠头选一盏河灯，留一句愿。'
    return '心愿已入河，继续逛逛吧。'
  })()

  const touch = (move: number, strafe: number) => ({
    onPointerDown: (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      sceneRef.current?.setTouch(move, strafe)
    },
    onPointerUp: () => sceneRef.current?.setTouch(0, 0),
    onPointerCancel: () => sceneRef.current?.setTouch(0, 0),
    onPointerLeave: () => sceneRef.current?.setTouch(0, 0),
  })

  const cat = hud.cat

  return (
    <div className={s.root}>
      <canvas
        ref={canvasRef}
        className={s.canvas}
        aria-label={t.title}
        onPointerDown={() => {
          // PRD §7.6: tapping blank space leaves photo mode without a keyboard.
          if (photo) togglePhoto()
        }}
      />

      <div className={`${s.vignette} ${photo ? s.vignettePhoto : ''}`} aria-hidden />

      {!entered && (
        <div className={s.gate}>
          <div className={s.gateScene} aria-hidden />
          <p className={s.kicker}>S1 · 入市</p>
          <h1 className={s.title}>{t.title}</h1>
          <p className={s.subtitle}>{t.subtitle}</p>
          <div className={s.gateBar}>
            <div className={s.meter}>
              <span style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <span className={s.meterText}>
              {ready ? t.ready : `${t.loading} ${Math.round(progress * 100)}%`}
            </span>
          </div>
          <button type="button" className={s.enter} onClick={enter} disabled={!ready}>
            {t.enter}
          </button>
          <p className={s.note}>{t.enterNote}</p>
        </div>
      )}

      {entered && (
        <>
          <header className={`${s.hud} ${photo || cat.active ? s.hidden : ''}`}>
            <div className={s.hudLeft}>
              <span className={s.brand}>{t.title}</span>
              <span className={s.steps}>
                <span className={hud.claimed ? s.stepOn : s.step}>
                  {hud.claimed ? t.done : t.todo} {t.step1}
                </span>
                <span className={hud.riddleSolved ? s.stepOn : s.step}>
                  {hud.riddleSolved ? t.done : t.todo} {t.step2}
                </span>
                <span className={hud.released ? s.stepOn : s.step}>
                  {hud.released ? t.done : t.todo} {t.step3}
                </span>
              </span>
            </div>
            <div className={s.chips}>
              {hud.style && <Chip label={t.style} value={hud.style} wide />}
              <Chip label={t.lanterns} value={String(hud.activeLanterns)} />
              {hud.cooldown > 0 && <Chip label={t.cooldown} value={`${hud.cooldown}s`} />}
            </div>
          </header>

          {!photo && !cat.active && <div className={s.suggest}>{suggestion}</div>}

          {cat.active && (
            <div className={`${s.catHud} ${photo ? s.hidden : ''}`}>
              <div className={s.catProgress}>
                <span className={cat.basketTipped ? s.stepOn : s.step}>
                  {cat.basketTipped ? t.done : t.todo} {t.catStep1}
                </span>
                <span className={cat.onShed ? s.stepOn : s.step}>
                  {cat.onShed ? t.done : t.todo} {t.catStep2}
                </span>
                {cat.completed && <span className={s.stepOn}>✓ {t.catDone}</span>}
              </div>
              <div className={s.catTools}>
                <button
                  type="button"
                  className={s.tool}
                  onClick={() => sceneRef.current?.resetCatAttempt()}
                >
                  {t.catReset}
                </button>
                <button
                  type="button"
                  className={s.tool}
                  onClick={() => sceneRef.current?.exitCat()}
                >
                  {t.catExit}
                </button>
              </div>
            </div>
          )}

          <div className={`${s.toolbar} ${photo || cat.active ? s.hidden : ''}`}>
            <div className={s.views}>
              {VIEWPOINTS.map((v, i) => (
                <button
                  key={v.name}
                  type="button"
                  className={i === view ? s.viewOn : s.view}
                  onClick={() => {
                    setView(i)
                    sceneRef.current?.setViewpoint(i)
                  }}
                >
                  {v.name}
                </button>
              ))}
            </div>
            <div className={s.tools}>
              <button type="button" className={s.tool} onClick={togglePhoto}>
                {photo ? t.exitPhoto : t.photo}
              </button>
              <button type="button" className={s.tool} onClick={toggleMute}>
                {muted ? t.unmute : t.mute}
              </button>
              <button
                type="button"
                className={s.tool}
                onClick={() => {
                  setView(0)
                  sceneRef.current?.returnToEntrance()
                }}
              >
                {t.back}
              </button>
            </div>
          </div>

          <div className={`${s.crosshair} ${photo || cat.active ? s.hidden : ''}`} aria-hidden />

          {prompt && !panel && !photo && (
            <div className={s.prompt}>
              <button
                type="button"
                className={
                  prompt.locked ? `${s.promptButton} ${s.promptButtonLocked}` : s.promptButton
                }
                onClick={() => sceneRef.current?.interact()}
              >
                <kbd>{t.ekey}</kbd>
                <span>{prompt.label}</span>
                {prompt.note && <span className={s.promptNote}>{prompt.note}</span>}
              </button>
            </div>
          )}

          {toast && !photo && <div className={s.toast}>{toast}</div>}

          {panel?.kind === 'release' ? (
            <div className={s.panelWrap} role="dialog" aria-modal="true" aria-label={panel.title}>
              <div className={s.panel}>
                <p className={s.panelTitle}>{panel.title}</p>
                <p className={s.panelBody}>{panel.body}</p>
                <div className={s.sectionLabel}>选一盏河灯</div>
                <div className={s.optionRow}>
                  {panel.options.map((o, i) => (
                    <button
                      key={o.label}
                      type="button"
                      className={panel.selectedStyle === i ? s.pillOn : s.pill}
                      onClick={() => sceneRef.current?.selectStyle(i)}
                    >
                      <span className={s.optionLabel}>{o.label}</span>
                      {o.note && <span className={s.optionNote}>{o.note}</span>}
                    </button>
                  ))}
                </div>
                <div className={s.sectionLabel}>留一句祝词</div>
                <div className={s.optionRow}>
                  {['平安顺遂', '阖家团圆', '前程似锦', '与君相逢'].map((label, i) => (
                    <button
                      key={label}
                      type="button"
                      className={panel.selectedBlessing === i ? s.pillOn : s.pill}
                      onClick={() => sceneRef.current?.selectBlessing(i)}
                    >
                      <span className={s.optionLabel}>{label}</span>
                    </button>
                  ))}
                </div>
                <p className={s.summary}>
                  {t.selected}：{panel.options[panel.selectedStyle ?? 0]?.label} ·{' '}
                  {['平安顺遂', '阖家团圆', '前程似锦', '与君相逢'][panel.selectedBlessing ?? 0]}
                </p>
                <button
                  type="button"
                  className={s.confirm}
                  onClick={() => sceneRef.current?.confirmRelease()}
                >
                  {panel.confirmLabel ?? t.confirm}
                </button>
                <button
                  type="button"
                  className={s.close}
                  onClick={() => sceneRef.current?.closePanel()}
                >
                  {t.close}
                </button>
              </div>
            </div>
          ) : (
            panel && (
              <div className={s.panelWrap} role="dialog" aria-modal="true" aria-label={panel.title}>
                <div className={s.panel}>
                  <p className={s.panelTitle}>{panel.title}</p>
                  <p className={s.panelBody}>{panel.body}</p>
                  <div className={s.options}>
                    {panel.options.map((o, i) => (
                      <button
                        key={o.label}
                        type="button"
                        className={o.disabled ? s.optionOff : s.option}
                        disabled={o.disabled}
                        onClick={() => choose(i)}
                      >
                        <span className={s.optionLabel}>{o.label}</span>
                        {o.note && <span className={s.optionNote}>{o.note}</span>}
                      </button>
                    ))}
                  </div>
                  {panel.hint && (
                    <p className={s.hint}>
                      <b>{t.hint}</b> {panel.hint}
                    </p>
                  )}
                  <button
                    type="button"
                    className={s.close}
                    onClick={() => sceneRef.current?.closePanel()}
                  >
                    {t.close}
                  </button>
                </div>
              </div>
            )
          )}

          <div
            className={`${s.dpad} ${photo ? s.hidden : ''}`}
            role="toolbar"
            aria-label={t.mobile}
          >
            <button type="button" className={`${s.pad} ${s.padUp}`} {...touch(1, 0)}>
              W
            </button>
            <button type="button" className={`${s.pad} ${s.padLeft}`} {...touch(0, -1)}>
              A
            </button>
            <button type="button" className={`${s.pad} ${s.padDown}`} {...touch(-1, 0)}>
              S
            </button>
            <button type="button" className={`${s.pad} ${s.padRight}`} {...touch(0, 1)}>
              D
            </button>
            <button
              type="button"
              className={`${s.pad} ${s.padAct}`}
              onClick={() => sceneRef.current?.interact()}
            >
              {cat.active ? cat.action || t.interact : t.interact}
            </button>
          </div>
        </>
      )}

      {photo && (
        <>
          <div className={s.frame} aria-hidden />
          <div className={`${s.watermark} ${photoHint ? '' : s.watermarkDim}`} aria-hidden>
            {language === 'zh' ? '桃源·上元灯会' : 'Shangyuan Lantern Night'}
          </div>
          {photoHint && <div className={s.photoHint}>{t.photoHint}</div>}
        </>
      )}
    </div>
  )
}

function Chip({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <span className={wide ? `${s.chip} ${s.chipWide}` : s.chip}>
      <span className={s.chipLabel}>{label}</span>
      <span className={s.chipValue}>{value}</span>
    </span>
  )
}
