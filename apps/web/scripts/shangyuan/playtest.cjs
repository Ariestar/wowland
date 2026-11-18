/**
 * Play the full preview loop through real input: claim → riddle → pick a lantern → release → show.
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

  await openScene(page)
  await enter(page, 1200)

  const fpsIdle = await measureFps(page)

  // 1. entrance: claim the lantern
  await teleport(page, 16.4, -120)
  await press('e')
  await shot('01-claim-panel')
  await answer('提起花灯')
  await shot('02-claimed')

  // 2. riddle stall: one wrong answer first to see the hint, then the full set
  await teleport(page, 13.4, 40)
  await page.evaluate(() => window.__shangyuan.lookAt(18.4, 40, 2.2))
  await page.waitForTimeout(400)
  await press('e')
  await answer('火树银花合') // wrong on purpose
  await shot('03-riddle-hint')
  await answer('更吹落、星如雨')
  for (const choice of ['正月十五', '莲花']) {
    await press('e')
    await answer(choice)
  }
  await shot('04-riddles-done')

  // 3. lantern tower: pick a style
  await teleport(page, 16.4, 78)
  await press('e')
  await shot('05-style-panel')
  await answer('莲花灯')

  // 4. quay: blessing and release
  await teleport(page, 13.4, 118)
  await press('e')
  await shot('06-blessing-panel')
  await answer('平安顺遂')
  await page.waitForTimeout(1200)
  await shot('07-released')

  const fpsAfterRelease = await measureFps(page)

  // 5. the show starts by itself a few seconds after the first release.
  // Stay at the quay: the show pans the camera to the tower, so walking away
  // would frame empty sky.
  for (const [wait, name] of [
    [2400, '08-show-iron-flower'],
    [2000, '09-show-fireworks'],
    [2400, '10-show-peak'],
    [2400, '11-show-late'],
    [4000, '12-show-final'],
  ]) {
    await page.waitForTimeout(wait)
    await shot(name)
  }

  // 6. cross the bridge on foot from the west bank to the east bank
  await teleport(page, -16.5, 10)
  await page.evaluate(() => window.__shangyuan.lookAt(21, 10, 5.6))
  await page.keyboard.down('Shift')
  await page.keyboard.down('w')
  const bridge = []
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(700)
    bridge.push(await page.evaluate(() => window.__shangyuan.where()))
  }
  await page.keyboard.up('w')
  await page.keyboard.up('Shift')
  await page.evaluate(() => window.__shangyuan.lookAt(0, 10, 5.6))
  await page.waitForTimeout(500)
  await shot('13-bridge-top')

  // Read the HUD header only: the body also carries Next.js dev-tool scripts.
  const hud = await page.evaluate(() => {
    const header = document.querySelector('header')
    return (header?.textContent ?? '').replace(/\s+/g, ' ').trim()
  })
  const stats = await page.evaluate(() => window.__shangyuan.stats())

  report(OUT, errors, {
    fpsIdle,
    fpsAfterRelease,
    fps: await measureFps(page),
    stats,
    bridge,
    hud,
  })
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
