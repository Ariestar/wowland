const { chromium } = require('@playwright/test')
const fs = require('fs')
const path = require('path')
const OUT = path.resolve(
  'test-results/shangyuan',
  'mobile-' + new Date().toISOString().replace(/[:.]/g, '-'),
)
fs.mkdirSync(OUT, { recursive: true })
;(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=d3d11'],
  })
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto((process.env.SITE_URL || 'http://127.0.0.1:3000') + '/')
  await page.waitForFunction(
    () => {
      const b = [...document.querySelectorAll('button')].find((x) =>
        x.textContent?.includes('进入灯会'),
      )
      return b && !b.disabled
    },
    null,
    { timeout: 120000 },
  )
  await page.waitForTimeout(1200)
  await page.screenshot({ path: path.join(OUT, 'm0-gate.png') })
  await page.getByRole('button', { name: '进入灯会' }).click()
  await page.waitForTimeout(2500)
  await page.screenshot({ path: path.join(OUT, 'm1-view.png') })
  await page.evaluate(() => window.__shangyuan.teleport(13, 18))
  await page.waitForTimeout(900)
  await page.screenshot({ path: path.join(OUT, 'm2-prompt.png') })
  const fps = await page.evaluate(
    () =>
      new Promise((r) => {
        let n = 0
        const t = performance.now()
        const f = () => {
          n++
          performance.now() - t < 1500
            ? requestAnimationFrame(f)
            : r(Math.round((n / (performance.now() - t)) * 1000))
        }
        requestAnimationFrame(f)
      }),
  )
  console.log('fps', fps, 'errors', errors.slice(0, 5), 'out', OUT)
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
