/**
 * Capture the preview: gate, six viewpoints, and one interaction pass.
 * Usage: node scripts/shangyuan/capture.cjs [url]
 * Output: test-results/shangyuan/<timestamp>/
 */
const { chromium } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

const OUT = path.resolve('test-results/shangyuan', new Date().toISOString().replace(/[:.]/g, '-'))
fs.mkdirSync(OUT, { recursive: true })

;(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: [
      '--enable-gpu',
      '--ignore-gpu-blocklist',
      '--use-angle=d3d11',
      '--autoplay-policy=no-user-gesture-required',
    ],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 300))
  })

  await page.goto((process.env.SITE_URL || 'http://127.0.0.1:3000') + '/')
  await page.waitForSelector('canvas', { timeout: 120000 })
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
  await page.waitForTimeout(1500)
  await page.screenshot({ path: path.join(OUT, '00-gate.png') })

  await page.getByRole('button', { name: '进入灯会' }).click()
  await page.waitForTimeout(2500)

  const views = ['入市', '灯市', '桥顶', '埠头', '对岸', '远景']
  for (let i = 0; i < views.length; i++) {
    const label = views[i]
    await page.evaluate((name) => {
      const b = [...document.querySelectorAll('button')].find((x) => x.textContent === name)
      b?.click()
    }, label)
    await page.waitForTimeout(1400)
    await page.screenshot({ path: path.join(OUT, `view-${i}-${label}.png`) })
  }

  // Interaction pass: walk to the entrance trigger and claim the lantern.
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => x.textContent === '入市')
    b?.click()
  })
  await page.waitForTimeout(800)
  await page.keyboard.press('e')
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(OUT, '10-claim-panel.png') })
  const claim = await page.locator('button', { hasText: '提起花灯' }).first()
  if (await claim.count()) {
    await claim.click()
    await page.waitForTimeout(700)
  }

  // Riddle stall
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => x.textContent === '灯市')
    b?.click()
  })
  await page.waitForTimeout(700)
  await page.evaluate(() => window.__shangyuan?.teleport?.(67, 10.5, 0))
  await page.waitForTimeout(900)
  await page.keyboard.press('e')
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(OUT, '11-riddle-panel.png') })
  const first = page.locator('button', { hasText: '更吹落、星如雨' }).first()
  if (await first.count()) {
    await first.click()
    await page.waitForTimeout(700)
  }

  const fps = await page.evaluate(
    () =>
      new Promise((resolve) => {
        let n = 0
        const t = performance.now()
        const step = () => {
          n++
          if (performance.now() - t < 1500) requestAnimationFrame(step)
          else resolve(Math.round((n / (performance.now() - t)) * 1000))
        }
        requestAnimationFrame(step)
      }),
  )

  console.log('fps', fps)
  console.log('errors', errors.slice(0, 8))
  console.log('out', OUT)
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
