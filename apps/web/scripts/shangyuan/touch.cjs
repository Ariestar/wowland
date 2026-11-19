/**
 * PRD §4.1/§12.2 touch path: holding the on-screen pad moves, releasing or
 * cancelling stops, and dragging the scene rotates the view.
 * Usage: node scripts/shangyuan/touch.cjs
 */
const {
  launch,
  outputDir,
  watchErrors,
  openScene,
  enter,
  shotter,
  report,
} = require('./harness.cjs')

;(async () => {
  const OUT = outputDir('touch')
  const browser = await launch()
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const client = await page.context().newCDPSession(page)
  const where = () => page.evaluate(() => window.__shangyuan.where())
  const yaw = () => page.evaluate(() => window.__shangyuan.yaw)
  const checks = {}

  const touchStart = (x, y) =>
    client.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x, y, radiusX: 8, radiusY: 8, force: 1 }],
    })
  const touchMove = (x, y) =>
    client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x, y, radiusX: 8, radiusY: 8, force: 1 }],
    })
  const touchEnd = () =>
    client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  const touchCancel = () =>
    client.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] })

  await openScene(page)
  await enter(page, 1200)

  const pad = await page.locator('button', { hasText: /^W$/ }).first().boundingBox()
  if (!pad) throw new Error('on-screen W pad not found')
  const px = pad.x + pad.width / 2
  const py = pad.y + pad.height / 2

  const start = await where()
  await touchStart(px, py)
  await page.waitForTimeout(700)
  await touchEnd()
  await page.waitForTimeout(300)
  const moved = await where()
  checks.holdMoves = Math.hypot(moved.x - start.x, moved.y - start.y) > 0.05
  await shot('01-touch-moved')

  await touchStart(px, py)
  await page.waitForTimeout(200)
  await touchCancel()
  const atCancel = await where()
  await page.waitForTimeout(700)
  const afterCancel = await where()
  checks.cancelStops = Math.hypot(afterCancel.x - atCancel.x, afterCancel.y - atCancel.y) < 0.02

  // Dragging the scene rotates the view (touch look).
  const yawBefore = await yaw()
  await touchStart(200, 400)
  await touchMove(260, 400)
  await page.waitForTimeout(120)
  await touchEnd()
  await page.waitForTimeout(300)
  const yawAfter = await yaw()
  checks.dragLooks = Math.abs(yawAfter - yawBefore) > 0.01
  await shot('02-touch-look')
  checks.noPageErrors = errors.length === 0

  report(OUT, errors, { checks })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
