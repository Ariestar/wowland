'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { VIEWPOINTS } from '@/lib/shangyuan/data'
import { ShangyuanScene } from '@/lib/shangyuan/scene'
import type { Panel, Phase, Prompt, SceneHud } from '@/lib/shangyuan/types'
import s from './ShangyuanWorld.module.css'

type Props = { language: 'zh' | 'en' }

const COPY = {
  zh: {
    title: '上元灯夜',
    subtitle: '提一盏灯，过一座桥，把心愿放进一条会发光的河。',
    enter: '进入灯会',
    enterNote: 'WASD 行走 · 鼠标转视角 · E 交互 · Esc 放开鼠标',
    loading: '灯正在一盏盏亮起',
    ready: '灯已点亮',
    wicks: '灯芯',
    riddles: '灯谜',
    released: '河灯',
    style: '手中灯',
    none: '未选',
    viewpoints: '机位',
    photo: '留影',
    exitPhoto: '退出留影',
    mute: '静音',
    unmute: '声音',
    help: '回到入口',
    ekey: 'E',
    interact: '交互',
    close: '先不看了',
    hint: '提示',
    mobile: '拖动画面转视角',
  },
  en: {
    title: 'Shangyuan Lantern Night',
    subtitle: 'Carry a lantern, cross a bridge, set a wish on a river of light.',
    enter: 'Enter the night market',
    enterNote: 'WASD to walk · mouse to look · E to interact · Esc to release the cursor',
    loading: 'Lighting the lanterns',
    ready: 'The lanterns are lit',
    wicks: 'Wicks',
    riddles: 'Riddles',
    released: 'Lanterns',
    style: 'Lantern',
    none: 'none',
    viewpoints: 'Views',
    photo: 'Photo',
    exitPhoto: 'Leave photo',
    mute: 'Mute',
    unmute: 'Sound',
    help: 'Back to start',
    ekey: 'E',
    interact: 'Interact',
    close: 'Not now',
    hint: 'Hint',
    mobile: 'Drag to look around',
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
    wicks: 0,
    riddles: 0,
    released: 0,
    style: '',
    blessing: '',
    showActive: false,
  })
  const [toast, setToast] = useState('')
  const [photo, setPhoto] = useState(false)
  const [muted, setMuted] = useState(false)
  const [view, setView] = useState(0)
  const toastTimer = useRef<number | null>(null)
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
    }
  }, [flash])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Escape' && photo) {
        setPhoto(false)
        sceneRef.current?.togglePhoto()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [photo])

  const enter = () => {
    setEntered(true)
    sceneRef.current?.setViewpoint(0)
  }

  const choose = (index: number) => sceneRef.current?.choose(index)

  const togglePhoto = () => {
    const next = sceneRef.current?.togglePhoto() ?? false
    setPhoto(next)
  }

  const toggleMute = () => {
    const next = !muted
    setMuted(next)
    sceneRef.current?.setMuted(next)
  }

  const phaseLabel: Record<Phase, string> = {
    idle: '入市',
    claimed: '已领灯',
    riddle: '猜谜',
    style: '已选灯',
    blessing: '写祝词',
    released: '已放灯',
    show: '灯会',
  }

  const touch = (move: number, strafe: number) => ({
    onPointerDown: (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      sceneRef.current?.setTouch(move, strafe)
    },
    onPointerUp: () => sceneRef.current?.setTouch(0, 0),
    onPointerCancel: () => sceneRef.current?.setTouch(0, 0),
    onPointerLeave: () => sceneRef.current?.setTouch(0, 0),
  })

  return (
    <div className={s.root}>
      <canvas ref={canvasRef} className={s.canvas} aria-label={t.title} />

      <div className={`${s.vignette} ${photo ? s.vignettePhoto : ''}`} aria-hidden />

      {!entered && (
        <div className={s.gate}>
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
          <header className={`${s.hud} ${photo ? s.hidden : ''}`}>
            <div className={s.hudLeft}>
              <span className={s.brand}>{t.title}</span>
              <span className={s.phase}>{phaseLabel[hud.phase]}</span>
            </div>
            <div className={s.chips}>
              <Chip label={t.wicks} value={String(hud.wicks)} />
              <Chip label={t.riddles} value={`${hud.riddles}/3`} />
              <Chip label={t.released} value={String(hud.released)} />
              <Chip label={t.style} value={hud.style || t.none} wide />
            </div>
          </header>

          <div className={`${s.toolbar} ${photo ? s.hidden : ''}`}>
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
                  sceneRef.current?.setViewpoint(0)
                }}
              >
                {t.help}
              </button>
            </div>
          </div>

          <div className={`${s.crosshair} ${photo ? s.hidden : ''}`} aria-hidden />

          {prompt && !panel && (
            <div className={`${s.prompt} ${photo ? s.hidden : ''}`}>
              <button
                type="button"
                className={s.promptButton}
                onClick={() => sceneRef.current?.interact()}
              >
                <kbd>{t.ekey}</kbd>
                <span>{prompt.label}</span>
              </button>
            </div>
          )}

          {toast && <div className={`${s.toast} ${photo ? s.hidden : ''}`}>{toast}</div>}

          {panel && (
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
              {t.interact}
            </button>
          </div>
        </>
      )}

      {photo && <div className={s.frame} aria-hidden />}
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
