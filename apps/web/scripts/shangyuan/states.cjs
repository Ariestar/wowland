/**
 * PRD T03/T04/T12 + §12.2 state and focus recovery:
 * locked reasons, repeat interactions, close-and-reopen riddle, and input
 * recovery after window blur.
 * Usage: node scripts/shangyuan/states.cjs
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

;(async () => {
  const OUT = outputDir('states')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const toast = () =>
    page.evaluate(() => document.querySelector('[class*="toast"]')?.textContent ?? '')
  const panelOpen = () => page.evaluate(() => !!document.querySelector('[class*="panelWrap"]'))
  const where = () => page.evaluate(() => window.__shangyuan.where())

  await openScene(page)
  await enter(page, 1000)
  const checks = {}

  // Locked reasons before claiming (T03/T12).
  await teleport(page, 13.5, -86.4)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  checks.quayLockedBeforeRiddle = (await toast()).includes('先猜中一道灯谜')
  checks.quayNoPanel = !(await panelOpen())

  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  checks.riddleLockedBeforeClaim = (await toast()).includes('先到牌坊点亮花灯')
  checks.riddleNoPanel = !(await panelOpen())

  await teleport(page, 16.2, -99.5)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  checks.catLockedBeforeClaim = (await toast()).includes('先点亮花灯')
  checks.catNotEntered = await page.evaluate(() => window.__shangyuan.stats().catMode === false)
  await shot('01-locked-states')

  // Claim, then repeat interaction must be informational only.
  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  await clickText(page, '点亮花灯', 700)
  checks.claimed = await page.evaluate(() => window.__shangyuan.stats().claimed === true)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  checks.claimRepeatToast = (await toast()).includes('花灯已经点亮')
  checks.claimRepeatNoPanel = !(await panelOpen())

  // Riddle: wrong, close, reopen, solve (T04 second half).
  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  await clickText(page, '纸船', 400)
  checks.hintVisible = await page.evaluate(() => !!document.querySelector('[class*="hint"]'))
  await clickText(page, '先不看了', 400)
  checks.closedWithoutSolve = await page.evaluate(
    () => window.__shangyuan.stats().riddleSolved === false,
  )
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  await clickText(page, '花灯', 700)
  checks.solvedAfterReopen = await page.evaluate(
    () => window.__shangyuan.stats().riddleSolved === true,
  )
  await page.keyboard.press('e')
  await page.waitForTimeout(300)
  checks.riddleRepeatToast = (await toast()).includes('这道谜已经解开')
  await shot('02-repeat-states')

  // Blur stops movement, then input recovers (PRD §12.2).
  const start = await where()
  await page.keyboard.down('w')
  await page.waitForTimeout(500)
  await page.keyboard.up('w')
  const moved = await where()
  await page.keyboard.down('w')
  await page.waitForTimeout(250)
  await page.evaluate(() => window.dispatchEvent(new Event('blur')))
  const atBlur = await where()
  await page.waitForTimeout(700)
  const afterBlur = await where()
  await page.keyboard.up('w')
  checks.movedBeforeBlur = Math.hypot(moved.x - start.x, moved.y - start.y) > 0.02
  checks.stoppedOnBlur = Math.hypot(afterBlur.x - atBlur.x, afterBlur.y - atBlur.y) < 0.02
  await page.keyboard.down('w')
  await page.waitForTimeout(400)
  await page.keyboard.up('w')
  const resumed = await where()
  checks.resumedAfterBlur = Math.hypot(resumed.x - afterBlur.x, resumed.y - afterBlur.y) > 0.02

  // Panel survives blur and Escape still closes it.
  await teleport(page, 13.5, -86.4)
  await page.keyboard.press('e')
  await page.waitForTimeout(400)
  const panelBeforeBlur = await panelOpen()
  await page.evaluate(() => window.dispatchEvent(new Event('blur')))
  await page.waitForTimeout(300)
  checks.panelSurvivesBlur = panelBeforeBlur && (await panelOpen())
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
  checks.escapeClosesPanel = !(await panelOpen())
  const beforeEscapeMove = await where()
  await page.keyboard.down('w')
  await page.waitForTimeout(400)
  await page.keyboard.up('w')
  const afterEscape = await where()
  checks.movedAfterEscape =
    Math.hypot(afterEscape.x - beforeEscapeMove.x, afterEscape.y - beforeEscapeMove.y) > 0.02
  await shot('03-focus-recovery')

  checks.noPageErrors = errors.length === 0
  report(OUT, errors, { checks })
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
