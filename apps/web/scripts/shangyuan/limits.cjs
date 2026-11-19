/**
 * PRD T10: five-lantern cap, 10 s cooldown and ~60 s recycling.
 * Slow by nature (real wall-clock rules), so it runs on demand:
 *   node scripts/shangyuan/limits.cjs
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
  report,
} = require('./harness.cjs')

const COOLDOWN_WAIT = 10600
const MAX = 5

;(async () => {
  const OUT = outputDir('limits')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const stats = () => page.evaluate(() => window.__shangyuan.stats())
  const toast = () =>
    page.evaluate(() => document.querySelector('[class*="toast"]')?.textContent ?? '')

  const openPanelAndRelease = async () => {
    await page.keyboard.press('e')
    await page.waitForTimeout(400)
    const opened = await page.evaluate(() => !!document.querySelector('[class*="panelWrap"]'))
    if (!opened) return false
    await clickText(page, '放出这盏灯', 300)
    return true
  }

  await openScene(page)
  await enter(page, 1000)
  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await clickText(page, '点亮花灯')
  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await clickText(page, '花灯')
  await teleport(page, 13.5, -86.4)
  await page.waitForTimeout(600)

  const releases = []
  let cooldownBlocked = false
  for (let i = 0; i < MAX; i++) {
    const ok = await openPanelAndRelease()
    await page.waitForTimeout(1700)
    const s = await stats()
    releases.push({ i: i + 1, ok, count: s.releaseCount, active: s.playerLanterns })
    if (i === 0) {
      // Immediately after a release the 10 s cooldown must refuse another one.
      await page.keyboard.press('e')
      await page.waitForTimeout(350)
      const panelDuringCooldown = await page.evaluate(
        () => !!document.querySelector('[class*="panelWrap"]'),
      )
      const toastDuringCooldown = await toast()
      cooldownBlocked = !panelDuringCooldown && /再等/.test(toastDuringCooldown)
      await shot('00-cooldown-refused')
    }
    if (i < MAX - 1) await page.waitForTimeout(COOLDOWN_WAIT)
  }
  await shot('01-five-active')

  // Sixth attempt: by the time the 5th completes and its cooldown elapses, the
  // oldest lantern is near or past its 60 s lifetime, so the cap is a safety
  // net rather than a reachable wall. What must hold: active never exceeds 5,
  // and once a lantern recycles a new release is allowed.
  await page.waitForTimeout(COOLDOWN_WAIT)
  const beforeAttempt = await stats()
  await page.keyboard.press('e')
  await page.waitForTimeout(400)
  const panelOpened = await page.evaluate(() => !!document.querySelector('[class*="panelWrap"]'))
  const attemptToast = await toast()
  await shot('02-cap-state')

  // Close the panel if it opened; we only need the state sample here.
  if (panelOpened) await clickText(page, '先不看了', 300)

  // Wait for the first lantern to pass its 60 s lifetime and check the HUD
  // count comes back down (recycle + HUD refresh).
  const born = Date.now()
  let recycled = null
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(2000)
    const s = await stats()
    if (s.playerLanterns < MAX) {
      recycled = { afterSeconds: Math.round((Date.now() - born) / 1000), ...s }
      break
    }
  }
  await shot('03-recycled')
  const afterRecycle = await stats()
  const rerelease = await openPanelAndRelease()
  await page.waitForTimeout(1800)
  const final = await stats()
  const checks = {
    fiveReleases: releases.length === MAX && releases.every((r) => r.ok),
    countsIncrease: releases.every((r, i) => r.count === i + 1),
    cooldownRejected: cooldownBlocked,
    activeNeverExceededCap: releases.every((r) => r.active <= MAX),
    recycledAtLeastOnce: recycled !== null,
    rereleaseAllowed: rerelease === true && final.releaseCount >= MAX + 1,
    noPageErrors: errors.length === 0,
  }

  report(OUT, errors, {
    checks,
    releases,
    beforeAttempt: {
      active: beforeAttempt.playerLanterns,
      cooldown: beforeAttempt.cooldown,
    },
    attempted: { panelOpened, toast: attemptToast },
    recycled,
    afterRecycle: afterRecycle.playerLanterns,
    rerelease,
    finalCount: final.releaseCount,
    finalActive: final.playerLanterns,
  })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
