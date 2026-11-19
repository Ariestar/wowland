/**
 * PRD F01/§12.1: a failed world load offers a retry that recovers in place.
 * Usage: node scripts/shangyuan/retry.cjs
 */
const {
  launch,
  desktopPage,
  outputDir,
  watchErrors,
  enter,
  shotter,
  report,
} = require('./harness.cjs')

const SITE = process.env.SITE_URL || 'http://127.0.0.1:3000'

;(async () => {
  const OUT = outputDir('retry')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const checks = {}

  // First load fails: the gate must show the retry control.
  await page.route('**/world.glb', (route) => route.abort())
  await page.goto(`${SITE}/`)
  await page.waitForSelector('canvas', { timeout: 60000 })
  await page.getByRole('button', { name: '重试加载' }).waitFor({ state: 'visible', timeout: 60000 })
  checks.retryShown = true
  checks.enterDisabled = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) =>
      x.textContent?.includes('进入灯会'),
    )
    return !!b && b.disabled
  })
  await shot('01-load-error')

  // Allow the GLB again and retry without a page reload.
  await page.unroute('**/world.glb')
  await page.getByRole('button', { name: '重试加载' }).click()
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
  checks.recovered = true
  await shot('02-recovered')
  await enter(page, 1200)
  checks.entered = await page.evaluate(() => document.querySelector('[class*="steps"]') !== null)
  // The aborted request is the test's own doing; anything else is a real error.
  const induced = errors.filter((e) => /ERR_FAILED|Failed to load resource/.test(e))
  const unexpected = errors.filter((e) => !/ERR_FAILED|Failed to load resource/.test(e))
  checks.inducedErrorSeen = induced.length > 0
  checks.noUnexpectedErrors = unexpected.length === 0

  report(OUT, unexpected, { checks, induced: induced.length })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
