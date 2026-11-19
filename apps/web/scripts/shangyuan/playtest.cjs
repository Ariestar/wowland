/**
 * Play the full MVP loop through real input (PRD §14 matrix):
 * claim → riddle (wrong then right) → release (style + blessing) →
 * cooldown/cap checks → cat trial (pounce, jump, descend, exit).
 * Usage: node scripts/shangyuan/playtest.cjs
 * Output: test-results/shangyuan/flow-<timestamp>/
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

;(async () => {
  const OUT = outputDir('flow')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)

  const press = async (key) => {
    await page.keyboard.press(key)
    await page.waitForTimeout(500)
  }
  const answer = (text) => clickText(page, text)
  const stats = () => page.evaluate(() => window.__shangyuan.stats())

  await openScene(page)
  await enter(page, 1200)

  const fpsIdle = await measureFps(page)

  // 1. entrance: claim the lantern (PRD §5)
  await teleport(page, 16.4, -123)
  await press('e')
  await shot('01-claim-panel')
  await answer('点亮花灯')
  await shot('02-claimed')

  // 2. riddle stall: wrong answer first to see the hint, then solve (PRD §6)
  await teleport(page, 15.6, -104)
  await page.evaluate(() => window.__shangyuan.lookAt(17.9, -103.9, 3))
  await press('e')
  await shot('03-riddle-panel')
  await answer('纸船') // wrong on purpose
  await shot('04-riddle-hint')
  await answer('花灯')
  await shot('05-riddles-done')

  // 3. quay: pick style + blessing in one panel, confirm the release (PRD §7)
  await teleport(page, 13.5, -86.4)
  await page.evaluate(() => window.__shangyuan.lookAt(11.5, -86.4, 1))
  await press('e')
  await shot('06-release-panel')
  await answer('纸船灯')
  await answer('前程似锦')
  await shot('07-release-selected')
  await answer('放出这盏灯')
  await page.waitForTimeout(2200)
  await shot('08-released')

  // 4. release guards: cooldown blocks the quick retry, then a later release
  // succeeds without redoing the riddle (PRD §7.5)
  const afterFirst = await stats()
  await press('e')
  await answer('放出这盏灯') // within cooldown: must be refused
  await page.waitForTimeout(600)
  const blockedStats = await stats()
  await page.waitForTimeout(10500) // let the 10 s cooldown elapse
  await press('e')
  await answer('放出这盏灯')
  await page.waitForTimeout(2400)
  const afterSecond = await stats()
  await shot('09-second-release')

  // 5. the show starts by itself a few seconds after the first release.
  for (const [wait, name] of [
    [2600, '10-show-iron-flower'],
    [2400, '11-show-fireworks'],
    [2400, '12-show-peak'],
  ]) {
    await page.waitForTimeout(wait)
    await shot(name)
  }

  // 6. photo mode: enter, leave by tapping the canvas (mobile path) (PRD §7.6)
  await clickText(page, '留影', 600)
  await shot('13-photo-mode')
  await page.mouse.click(720, 450)
  await page.waitForTimeout(500)
  await shot('14-photo-exit')

  // 7. cat trial: mask → walk to the basket → pounce → paw print → shed → exit
  await teleport(page, 16.2, -99.5)
  await press('e') // enter cat mode
  await shot('15-cat-enter')
  // Cat spawn (17.0, -97.4) faces the basket (18.1, -95.4), ~2.3 m away.
  await page.keyboard.down('w')
  await page.waitForTimeout(700)
  await page.keyboard.up('w')
  await page.waitForTimeout(300)
  await press('e') // pounce the basket
  await page.waitForTimeout(900)
  await shot('16-cat-pounce')
  // Turn toward the paw print (18.5, -93.7) and close the gap to < 1.6 m.
  await page.evaluate(() => window.__shangyuan.lookAt(18.5, -93.7))
  await page.keyboard.down('w')
  await page.waitForTimeout(350)
  await page.keyboard.up('w')
  await page.waitForTimeout(300)
  await press('e') // leap to the shed
  await page.waitForTimeout(1100)
  await shot('17-cat-shed')
  const catStats = await stats()
  await press('e') // descend
  await page.waitForTimeout(900)
  await clickText(page, '退出狸奴试玩', 700)
  await shot('18-cat-exit')

  const fpsAfterRelease = await measureFps(page)
  const finalStats = await stats()
  const checks = {
    claimed: finalStats.claimed === true,
    riddleSolved: finalStats.riddleSolved === true,
    released: finalStats.released === true,
    twoReleases: finalStats.releaseCount >= 2,
    catCompleted: finalStats.catCompleted === true,
    catModeExited: finalStats.catMode === false,
    noPageErrors: errors.length === 0,
  }

  report(OUT, errors, {
    checks,
    fpsIdle,
    fpsAfterRelease,
    afterFirst,
    blockedStats,
    afterSecond,
    catStats,
    finalStats,
    fps: await measureFps(page),
  })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
