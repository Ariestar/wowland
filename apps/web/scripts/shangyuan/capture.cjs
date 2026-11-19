/**
 * Capture the MVP preview: gate, local viewpoints, and one interaction pass.
 * Usage: node scripts/shangyuan/capture.cjs
 * Output: test-results/shangyuan/capture-<timestamp>/
 */
const {
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
} = require('./harness.cjs')

const VIEWS = ['入市', '灯谜', '埠头', '灯街']

;(async () => {
  const OUT = outputDir('capture')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)

  await openScene(page, 1500)
  await shot('00-gate')
  await enter(page, 2500)

  for (const [index, label] of VIEWS.entries()) {
    await page.evaluate((name) => {
      const button = [...document.querySelectorAll('button')].find((b) => b.textContent === name)
      button?.click()
    }, label)
    await page.waitForTimeout(1400)
    await shot(`view-${index}-${label}`)
  }

  // Interaction pass: stand at the entrance trigger and claim the lantern.
  await clickText(page, '入市', 800)
  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await page.waitForTimeout(600)
  await shot('10-claim-panel')
  await clickText(page, '点亮花灯', 700)

  // Riddle stall: stand before the authored stall so it reads whole.
  await teleport(page, 15.6, -104, 900)
  await page.evaluate(() => window.__shangyuan.lookAt(17.9, -103.9, 3))
  await page.waitForTimeout(400)
  await shot('10b-riddle-stall')
  await page.keyboard.press('e')
  await page.waitForTimeout(600)
  await shot('11-riddle-panel')

  report(OUT, errors, { fps: await measureFps(page) })
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
