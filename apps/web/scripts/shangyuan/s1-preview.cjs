/**
 * S1 acceptance capture: spawn view, proximity highlight, ignition, result and photo mode.
 * Usage: node scripts/shangyuan/s1-preview.cjs
 * Output: test-results/shangyuan/s1-<timestamp>/
 */
const {
  launch,
  desktopPage,
  outputDir,
  watchErrors,
  openScene,
  enter,
  teleport,
  shotter,
  measureFps,
  report,
} = require('./harness.cjs')

;(async () => {
  const OUT = outputDir('s1')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)

  await openScene(page, 1200)
  await shot('00-gate')
  await enter(page, 1800)
  await shot('01-spawn')

  await teleport(page, 14.15, -126.2, 700)
  await page.evaluate(() => window.__shangyuan.lookAt(14.15, -124.2, 2.35))
  await page.waitForTimeout(500)
  await shot('02-approach')

  const prompt = await page.getByRole('button', { name: /点亮花灯/ }).count()
  await page.keyboard.press('e')
  await page.waitForTimeout(450)
  await shot('03-igniting')
  await page.waitForTimeout(900)
  await shot('04-lit')

  const tools = page.locator('button')
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent === '留影')
    button?.click()
  })
  await page.waitForTimeout(500)
  await shot('05-photo')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  await page.evaluate(() => window.__shangyuan.returnToEntrance())
  await page.waitForTimeout(700)
  await shot('06-reset')

  const stats = await page.evaluate(() => window.__shangyuan.stats())
  const hud = await page.evaluate(() =>
    document.querySelector('header')?.textContent?.replace(/\s+/g, ' ').trim(),
  )
  report(OUT, errors, {
    fps: await measureFps(page),
    stats,
    promptFound: prompt > 0,
    hud,
    toolCount: await tools.count(),
  })
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
