/**
 * PRD T06: every lantern style × blessing combination shows the right pair in
 * the merged release panel. Panel-only, so it is fast and needs no cooldown.
 * Usage: node scripts/shangyuan/combos.cjs
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

const STYLES = ['莲花灯', '纸船灯', '鱼龙灯']
const BLESSINGS = ['平安顺遂', '阖家团圆', '前程似锦', '与君相逢']

;(async () => {
  const OUT = outputDir('combos')
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const shot = shotter(page, OUT)
  const rows = []

  await openScene(page)
  await enter(page, 1000)
  await teleport(page, 16.4, -123)
  await page.keyboard.press('e')
  await clickText(page, '点亮花灯')
  await teleport(page, 15.6, -104)
  await page.keyboard.press('e')
  await clickText(page, '花灯')
  await teleport(page, 13.5, -86.4)
  await page.waitForTimeout(500)
  await page.keyboard.press('e')
  await page.waitForTimeout(500)

  for (const style of STYLES) {
    for (const blessing of BLESSINGS) {
      await clickText(page, style, 160)
      await clickText(page, blessing, 160)
      const summary = await page.evaluate(
        () => document.querySelector('[class*="summary"]')?.textContent ?? '',
      )
      rows.push({
        style,
        blessing,
        summary: summary.trim(),
        ok: summary.includes(style) && summary.includes(blessing),
      })
    }
  }
  await shot('combos-final')

  const failed = rows.filter((r) => !r.ok)
  report(OUT, errors, {
    total: rows.length,
    passed: rows.length - failed.length,
    failures: failed,
  })
  await browser.close()
  // A verification script must fail the command when its checks fail.
  if (failed.length > 0 || errors.length > 0) process.exit(1)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
