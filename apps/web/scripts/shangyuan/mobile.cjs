/**
 * Check the mobile layout: gate screen, first view, and the interaction prompt.
 * Usage: node scripts/shangyuan/mobile.cjs
 * Output: test-results/shangyuan/mobile-<timestamp>/
 */
const {
  launch,
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
  const OUT = outputDir('mobile')
  const browser = await launch()
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)

  await openScene(page, 1200)
  await shot('m0-gate')
  await enter(page, 2500)
  await shot('m1-view')
  await teleport(page, 16.4, -123, 900)
  await shot('m2-prompt')

  report(OUT, errors, { fps: await measureFps(page) })
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
