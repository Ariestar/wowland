/**
 * Play the full preview loop through real input: claim → riddle → pick a lantern → release → show.
 * Usage: node scripts/shangyuan/playtest.cjs [url]
 */
const { chromium } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

const OUT = path.resolve('test-results/shangyuan', `flow-${new Date().toISOString().replace(/[:.]/g, '-')}`)
fs.mkdirSync(OUT, { recursive: true })

const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${name}.png`) })

;(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=d3d11', '--autoplay-policy=no-user-gesture-required'],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200))
  })

  await page.goto((process.env.SITE_URL || 'http://127.0.0.1:3000') + '/')
  await page.waitForFunction(() => window.__shangyuan, null, { timeout: 120000 })
  await page.waitForFunction(
    () => {
      const b = [...document.querySelectorAll('button')].find((x) => x.textContent?.includes('进入灯会'))
      return b && !b.disabled
    },
    null,
    { timeout: 120000 },
  )
  await page.getByRole('button', { name: '进入灯会' }).click()
  await page.waitForTimeout(1200)

  const measure = () =>
    page.evaluate(
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

  const go = async (x, y) => {
    await page.evaluate(([x, y]) => window.__shangyuan.teleport(x, y), [x, y])
    await page.waitForTimeout(500)
  }
  const press = async (key) => {
    await page.keyboard.press(key)
    await page.waitForTimeout(500)
  }
  const clickText = async (text) => {
    const b = page.locator('button', { hasText: text }).first()
    if (await b.count()) {
      await b.click()
      await page.waitForTimeout(600)
      return true
    }
    return false
  }

  const fpsIdle = await measure()

  // 1. entrance: claim the lantern
  await go(13, 18)
  await press('e')
  await shot(page, '01-claim-panel')
  await clickText('提起花灯')
  await shot(page, '02-claimed')

  // 2. riddle stall: three questions, one wrong answer first to see the hint
  await go(67, 10.5)
  await press('e')
  await clickText('火树银花合') // wrong on purpose
  await shot(page, '03-riddle-hint')
  await clickText('更吹落、星如雨')
  for (let i = 0; i < 2; i++) {
    await press('e')
    await clickText(i === 0 ? '正月十五' : '莲花')
  }
  await shot(page, '04-riddles-done')

  // 3. lantern tower: pick a style
  await go(96, 16)
  await press('e')
  await shot(page, '05-style-panel')
  await clickText('莲花灯')

  // 4. quay: blessing and release
  await go(125, 10)
  await press('e')
  await shot(page, '06-blessing-panel')
  await clickText('平安顺遂')
  await page.waitForTimeout(1200)
  await shot(page, '07-released')

  const fpsAfterRelease = await measure()

  // 4b. cross the bridge on foot (deck height + rail collision)
  await page.evaluate(() => window.__shangyuan.teleport(90, 0))
  await page.waitForTimeout(500)
  // From the crown, look east along the river: lanterns, banks and reflections in one frame.
  await page.evaluate(() => window.__shangyuan.lookAt(152, 3, 2.4))
  await page.keyboard.down('w')
  const bridge = []
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(700)
    bridge.push(await page.evaluate(() => window.__shangyuan.where()))
  }
  await page.keyboard.up('w')
  console.log('bridge', JSON.stringify(bridge))
  await shot(page, '07b-bridge-top')

  // 5. the show starts by itself a few seconds after the first release
  await page.waitForTimeout(4200)
  await shot(page, '08-show-iron-flower')
  await page.waitForTimeout(4000)
  await shot(page, '09-show-fireworks')
  await page.waitForTimeout(6000)
  await shot(page, '10-show-peak')
  await page.waitForTimeout(7000)
  await shot(page, '11-show-late')

  const state = await page.evaluate(() => {
    const text = document.body.innerText
    return { hud: text.slice(0, 400), toast: text.includes('灯会') }
  })
  const fps = await measure()

  const stats = await page.evaluate(() => window.__shangyuan.stats())
  console.log('fpsIdle', fpsIdle, 'fpsAfterRelease', fpsAfterRelease)
  console.log('stats', JSON.stringify(stats))
  console.log('fps', fps)
  console.log('hud', state.hud.replace(/\n+/g, ' | '))
  console.log('errors', errors.slice(0, 8))
  console.log('out', OUT)
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
