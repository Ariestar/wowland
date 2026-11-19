/**
 * PRD §4.4 / T11: the whole main line on a landscape phone viewport,
 * including the scrollable release panel and the photo-mode hint fade.
 * Usage: node scripts/shangyuan/landscape.cjs
 */
const {
  launch,
  outputDir,
  watchErrors,
  openScene,
  enter,
  clickText,
  teleport,
  shotter,
  report,
} = require('./harness.cjs')

;(async () => {
  const OUT = outputDir('landscape')
  const browser = await launch()
  const page = await browser.newPage({
    viewport: { width: 844, height: 390 },
    hasTouch: true,
  })
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const stats = () => page.evaluate(() => window.__shangyuan.stats())
  const checks = {}

  await openScene(page)
  await enter(page, 1000)
  await shot('01-landscape')

  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await clickText(page, '点亮花灯', 700)
  checks.claimed = (await stats()).claimed === true

  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await clickText(page, '花灯', 700)
  checks.solved = (await stats()).riddleSolved === true

  await teleport(page, 13.5, -86.4)
  await page.waitForTimeout(600)
  await page.keyboard.press('e')
  await page.waitForTimeout(500)
  checks.panelScrolls = await page.evaluate(() => {
    const el = document.querySelector('[class*="panel"]:not([class*="panelWrap"])')
    return !!el && el.scrollHeight > el.clientHeight
  })
  await shot('02-release-panel')
  await clickText(page, '鱼龙灯', 200)
  await clickText(page, '前程似锦', 200)
  await page.evaluate(() => {
    const el = document.querySelector('[class*="panel"]:not([class*="panelWrap"])')
    if (el) el.scrollTop = el.scrollHeight
  })
  const confirmReachable = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) =>
      x.textContent?.includes('放出这盏灯'),
    )
    if (!b) return false
    const r = b.getBoundingClientRect()
    return r.top >= 0 && r.bottom <= innerHeight
  })
  checks.confirmReachable = confirmReachable
  await clickText(page, '放出这盏灯', 400)
  await page.waitForTimeout(2200)
  checks.released = (await stats()).released === true
  await shot('03-released')

  // Photo mode: hint shows for ~3 s then fades; watermark stays.
  await clickText(page, '留影', 400)
  checks.photoHintVisible = await page.evaluate(
    () => !!document.querySelector('[class*="photoHint"]'),
  )
  checks.photoToastHidden = await page.evaluate(() => !document.querySelector('[class*="toast"]'))
  await shot('04-photo')
  await page.waitForTimeout(3400)
  checks.photoHintFaded = await page.evaluate(() => !document.querySelector('[class*="photoHint"]'))
  checks.watermarkStays = await page.evaluate(
    () => !!document.querySelector('[class*="watermark"]'),
  )
  await shot('05-photo-faded')
  // Exit by tapping blank space, as a phone user would.
  await page.touchscreen.tap(420, 200)
  await page.waitForTimeout(500)
  checks.photoExited = await page.evaluate(() => !document.querySelector('[class*="watermark"]'))

  // Cat trial still works at this viewport.
  await teleport(page, 16.2, -99.5)
  await page.keyboard.press('e')
  await page.waitForTimeout(900)
  checks.catEntered = (await stats()).catMode === true
  await page.keyboard.down('w')
  await page.waitForTimeout(700)
  await page.keyboard.up('w')
  await page.waitForTimeout(300)
  await page.keyboard.press('e')
  await page.waitForTimeout(900)
  checks.catTipped = (await stats()).catTipped === true
  await shot('06-cat')
  await clickText(page, '退出狸奴试玩', 600)
  checks.catExited = (await stats()).catMode === false
  checks.progressKept = await page.evaluate(() => {
    const s = window.__shangyuan.stats()
    return s.claimed && s.riddleSolved && s.released
  })
  checks.noPageErrors = errors.length === 0

  report(OUT, errors, { checks })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
