/**
 * PRD §12.1 continuous-play soak: default 3 minutes, set SOAK_MINUTES=10 for
 * the acceptance run. Repeats release / photo / cat interactions and checks
 * that nothing accumulates or breaks.
 * Usage: node scripts/shangyuan/soak.cjs
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

const MINUTES = Number(process.env.SOAK_MINUTES || 3)

;(async () => {
  const OUT = outputDir('soak')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const stats = () => page.evaluate(() => window.__shangyuan.stats())
  const samples = []
  const checks = {}
  const failures = []

  await openScene(page)
  await enter(page, 1200)
  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await clickText(page, '点亮花灯', 700)
  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await clickText(page, '花灯', 700)

  // Warm-up: the cat prototype's placeholder geometry uploads on first render,
  // which is a one-time step and must not be counted as a leak.
  await teleport(page, 16.2, -99.5)
  await page.keyboard.press('e')
  await page.waitForTimeout(900)
  await page.keyboard.down('w')
  await page.waitForTimeout(600)
  await page.keyboard.up('w')
  await page.keyboard.press('e')
  await page.waitForTimeout(800)
  await clickText(page, '退出狸奴试玩', 500)
  await teleport(page, 13.5, -86.4)
  await page.waitForTimeout(400)

  const endAt = Date.now() + MINUTES * 60 * 1000
  let cycles = 0
  let releases = 0
  let catTrips = 0
  let photos = 0

  while (Date.now() < endAt) {
    cycles++
    // Release whenever allowed.
    await teleport(page, 13.5, -86.4)
    await page.waitForTimeout(400)
    await page.keyboard.press('e')
    await page.waitForTimeout(350)
    const panel = await page.evaluate(() => !!document.querySelector('[class*="panelWrap"]'))
    if (panel) {
      const before = (await stats()).releaseCount
      await clickText(page, '放出这盏灯', 250)
      await page.waitForTimeout(1700)
      const after = await stats()
      if (after.releaseCount === before + 1) releases++
      else failures.push(`release@${cycles}`)
    } else {
      await page.waitForTimeout(600)
    }

    // Photo in/out, confirmed by the watermark appearing and disappearing.
    await clickText(page, '留影', 250)
    await page.waitForTimeout(350)
    const photoIn = await page.evaluate(() => !!document.querySelector('[class*="watermark"]'))
    await page.mouse.click(720, 450)
    await page.waitForTimeout(300)
    const photoOut = await page.evaluate(() => !document.querySelector('[class*="watermark"]'))
    if (photoIn && photoOut) photos++
    else failures.push(`photo@${cycles}`)

    // Cat trip every other cycle, confirmed by catMode entering and leaving.
    if (cycles % 2 === 0) {
      await teleport(page, 16.2, -99.5)
      await page.keyboard.press('e')
      await page.waitForTimeout(800)
      const entered = (await stats()).catMode === true
      await page.keyboard.down('w')
      await page.waitForTimeout(700)
      await page.keyboard.up('w')
      await page.keyboard.press('e')
      await page.waitForTimeout(800)
      await clickText(page, '退出狸奴试玩', 500)
      const exited = (await stats()).catMode === false
      if (entered && exited) catTrips++
      else failures.push(`cat@${cycles}`)
    }

    const s = await stats()
    samples.push({
      t: Math.round((Date.now() - (endAt - MINUTES * 60 * 1000)) / 1000),
      releases,
      lanterns: s.lanterns,
      playerLanterns: s.playerLanterns,
      geometries: s.geometries,
      textures: s.textures,
      drawCalls: s.drawCalls,
      catMode: s.catMode,
    })
  }

  await shot('01-soak-end')
  const first = samples[0]
  const last = samples[samples.length - 1]
  const finalStats = await stats()
  // Input still works after the soak.
  const before = await page.evaluate(() => window.__shangyuan.where())
  await page.keyboard.down('w')
  await page.waitForTimeout(500)
  await page.keyboard.up('w')
  const after = await page.evaluate(() => window.__shangyuan.where())

  checks.ranEnough = samples.length >= Math.max(3, MINUTES * 2)
  checks.ownerCapHeld = samples.every((s) => s.playerLanterns <= 5)
  checks.lanternCapHeld = samples.every((s) => s.lanterns <= 70)
  checks.noTextureLeak = last.textures - first.textures <= 5
  checks.noGeometryLeak = last.geometries - first.geometries <= 5
  checks.releasesHappened = releases >= 2
  checks.catTripsHappened = catTrips >= 1
  checks.noActionFailures = failures.length === 0
  checks.inputRecovered = Math.hypot(after.x - before.x, after.y - before.y) > 0.02
  checks.catModeOff = finalStats.catMode === false
  checks.noPageErrors = errors.length === 0

  report(OUT, errors, {
    checks,
    failures,
    minutes: MINUTES,
    cycles,
    releases,
    photos,
    catTrips,
    first,
    last,
    fps: await measureFps(page),
  })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
