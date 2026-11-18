/**
 * Shared Playwright harness for the Lantern River verification scripts.
 * Keeps launch flags, page wiring, gate waiting, screenshots and FPS sampling in one place.
 */
const { chromium } = require('@playwright/test')
const fs = require('node:fs')
const path = require('node:path')

const SITE = process.env.SITE_URL || 'http://127.0.0.1:3000'
const RESULTS = path.resolve('test-results/shangyuan')

const GPU_ARGS = [
  '--enable-gpu',
  '--ignore-gpu-blocklist',
  '--use-angle=d3d11',
  '--autoplay-policy=no-user-gesture-required',
]

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-')
}

function outputDir(prefix) {
  const dir = path.join(RESULTS, `${prefix}-${timestamp()}`)
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

function launch() {
  return chromium.launch({ channel: 'chrome', headless: true, args: GPU_ARGS })
}

function desktopPage(browser) {
  return browser.newPage({ viewport: { width: 1440, height: 900 } })
}

function watchErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 240)}`)
  })
  return errors
}

async function waitForGate(page) {
  await page.waitForSelector('canvas', { timeout: 120000 })
  await page.waitForFunction(
    () => {
      const button = [...document.querySelectorAll('button')].find((b) =>
        b.textContent?.includes('进入灯会'),
      )
      return button && !button.disabled
    },
    null,
    { timeout: 120000 },
  )
}

/** Load the page, wait for the assets, and optionally let the first frame settle. */
async function openScene(page, settle = 0) {
  await page.goto(`${SITE}/`)
  await waitForGate(page)
  if (settle) await page.waitForTimeout(settle)
}

async function enter(page, settle = 1200) {
  await page.getByRole('button', { name: '进入灯会' }).click()
  await page.waitForTimeout(settle)
}

/** Click the first button whose text contains `text`; false when it is absent. */
async function clickText(page, text, settle = 600) {
  const button = page.locator('button', { hasText: text }).first()
  if (!(await button.count())) return false
  await button.click()
  await page.waitForTimeout(settle)
  return true
}

/** Jump the player to a Blender (x, y) spot; the scene samples the ground height. */
async function teleport(page, x, y, settle = 500) {
  await page.evaluate(([px, py]) => window.__shangyuan.teleport(px, py), [x, y])
  await page.waitForTimeout(settle)
}

function shotter(page, dir) {
  return (name) => page.screenshot({ path: path.join(dir, `${name}.png`) })
}

async function measureFps(page, ms = 1500) {
  return page.evaluate(
    (duration) =>
      new Promise((resolve) => {
        let frames = 0
        const start = performance.now()
        const step = () => {
          frames++
          if (performance.now() - start < duration) requestAnimationFrame(step)
          else resolve(Math.round((frames / (performance.now() - start)) * 1000))
        }
        requestAnimationFrame(step)
      }),
    ms,
  )
}

function report(out, errors, extra = {}) {
  console.log(JSON.stringify({ ...extra, errors: errors.slice(0, 8), out }, null, 2))
}

module.exports = {
  launch,
  desktopPage,
  outputDir,
  watchErrors,
  openScene,
  enter,
  clickText,
  teleport,
  shotter,
  measureFps,
  report,
}
