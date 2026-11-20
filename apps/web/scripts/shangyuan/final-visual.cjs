/**
 * Real-entry visual gate for the public-kit detail upgrade.
 * Drives the shipped page from the entry button, captures two player views,
 * and verifies the new formal assets, readable pixels and live input.
 *
 * Usage:
 *   OUT_DIR=<dir> node scripts/shangyuan/final-visual.cjs
 */
const fs = require('node:fs')
const path = require('node:path')

const { launch, desktopPage, watchErrors, openScene, enter, measureFps } = require('./harness.cjs')

const OUT = process.env.OUT_DIR
  ? path.resolve(process.env.OUT_DIR)
  : path.resolve('test-results/shangyuan/final-visual')
const VIEWS = ['入市', '灯街']
fs.mkdirSync(OUT, { recursive: true })

function clickView(page, name) {
  return page.evaluate((label) => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent === label)
    button?.click()
    return Boolean(button)
  }, name)
}

async function measureOfficialVisibility(page) {
  return page.evaluate(() => {
    const app = window.__shangyuan
    const camera = app?.camera
    const group = app?.publicScenery?.object
    if (!camera || !group) return null
    camera.updateMatrixWorld()
    const visible = {
      sakura: 0,
      willow: 0,
      bamboo: 0,
      grass: 0,
      shrubs: 0,
      pavilions: 0,
      corridors: 0,
    }
    group.traverse((object) => {
      if (!object.isMesh || !object.name.startsWith('AwcScenery_')) return
      const kind = object.name.slice('AwcScenery_'.length)
      if (!(kind in visible)) return
      const geometry = object.geometry
      if (!geometry.boundingSphere) geometry.computeBoundingSphere()
      const sphere = geometry.boundingSphere
      if (!sphere) return
      const Matrix4 = object.matrixWorld.constructor
      const count = object.isInstancedMesh ? object.count : 1
      for (let i = 0; i < count; i++) {
        const world = object.matrixWorld.clone()
        if (object.isInstancedMesh) {
          const instance = new Matrix4()
          object.getMatrixAt(i, instance)
          world.multiply(instance)
        }
        const ndc = sphere.center.clone().applyMatrix4(world).project(camera)
        if (ndc.z >= -1 && ndc.z <= 1 && Math.abs(ndc.x) <= 1.05 && Math.abs(ndc.y) <= 1.05) {
          visible[kind]++
        }
      }
    })
    return visible
  })
}

async function analyseScreenshot(page, buffer) {
  return page.evaluate(async (base64) => {
    const img = new Image()
    img.src = `data:image/png;base64,${base64}`
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = 240
    canvas.height = 150
    const ctx = canvas.getContext('2d')
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data
    let lit = 0
    let colorful = 0
    let luma = 0
    const count = data.length / 4
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i]
      const g = data[i + 1]
      const b = data[i + 2]
      const max = Math.max(r, g, b)
      const min = Math.min(r, g, b)
      luma += (r + g + b) / 3
      if (max > 24) lit++
      if (max > 50 && max - min > 18) colorful++
    }
    return {
      litRatio: +(lit / count).toFixed(4),
      colorfulRatio: +(colorful / count).toFixed(4),
      meanLuma: +(luma / count).toFixed(2),
    }
  }, buffer.toString('base64'))
}

;(async () => {
  const browser = await launch()
  const page = await desktopPage(browser)
  const errors = watchErrors(page)
  const assetResponses = {}
  page.on('response', (response) => {
    const url = response.url()
    if (url.includes('blossom_petal.jpg')) assetResponses.petal = response.status()
    if (url.includes('SM_Prop_Lantern_Hung_01.glb')) assetResponses.kitLantern = response.status()
    for (const name of [
      'sakura-tree',
      'willow',
      'bamboo',
      'grass-clump',
      'shrub',
      'wood-pavilion',
      'crossing-corridor',
    ]) {
      if (url.includes(`/library/${name}.glb`)) assetResponses[name] = response.status()
    }
    if (url.includes('basis_transcoder')) assetResponses.basis = response.status()
  })

  await openScene(page, 1200)
  await enter(page, 2500)

  const canvas = await page.evaluate(() => {
    const element = document.querySelector('canvas')
    const rect = element.getBoundingClientRect()
    return {
      css: [Math.round(rect.width), Math.round(rect.height)],
      buffer: [element.width, element.height],
      viewportFill: +((rect.width * rect.height) / (innerWidth * innerHeight)).toFixed(3),
    }
  })

  const samples = []
  for (const [index, label] of VIEWS.entries()) {
    const found = await clickView(page, label)
    await page.waitForTimeout(1400)
    const image = await page.screenshot({ path: path.join(OUT, `view-${index}-${label}.png`) })
    const pixels = await analyseScreenshot(page, image)
    const stats = await page.evaluate(() => window.__shangyuan.stats())
    samples.push({
      view: label,
      viewButtonFound: found,
      pixels,
      stats,
      officialVisibility: await measureOfficialVisibility(page),
      fps: await measureFps(page, 1200),
    })
  }

  const before = await page.evaluate(() => window.__shangyuan.where())
  await page.keyboard.down('w')
  await page.waitForTimeout(650)
  await page.keyboard.up('w')
  const after = await page.evaluate(() => window.__shangyuan.where())
  const inputDelta = Math.hypot(after.x - before.x, after.y - before.y)

  const suspiciousHooks = await page.evaluate(() =>
    Object.keys(window).filter((key) =>
      /finalvisual|temporary|testhook|__probe|__hook|__inject/i.test(key),
    ),
  )

  const checks = {
    canvasSized: canvas.css[0] >= 1440 && canvas.css[1] >= 900,
    canvasFillsViewport: canvas.viewportFill >= 0.85,
    assetsLoaded: assetResponses.petal === 200 && assetResponses.kitLantern === 200,
    officialSceneryLoaded: [
      'sakura-tree',
      'willow',
      'bamboo',
      'grass-clump',
      'shrub',
      'wood-pavilion',
      'crossing-corridor',
    ].every((name) => assetResponses[name] === 200),
    basisTranscoderLoaded: assetResponses.basis === 200,
    publicSceneryInStats: samples.every((s) => {
      const scenery = s.stats.publicScenery
      return (
        scenery &&
        scenery.sakura >= 4 &&
        scenery.willow >= 3 &&
        scenery.bamboo >= 8 &&
        scenery.grass >= 8 &&
        scenery.shrubs >= 3 &&
        scenery.pavilions >= 1 &&
        scenery.corridors >= 3
      )
    }),
    officialSceneryVisible: samples.some((s) => {
      const visible = s.officialVisibility
      return (
        visible &&
        visible.sakura > 0 &&
        visible.willow > 0 &&
        visible.bamboo > 0 &&
        visible.grass > 0 &&
        visible.shrubs > 0 &&
        visible.pavilions > 0 &&
        visible.corridors > 0
      )
    }),
    detailInStats: samples.every(
      (s) => s.stats.ambientPetals > 0 && s.stats.entranceKitLanterns >= 4,
    ),
    pixelsReadable: samples.every(
      (s) => s.pixels.litRatio > 0.2 && s.pixels.colorfulRatio > 0.03 && s.pixels.meanLuma > 8,
    ),
    viewsFound: samples.every((s) => s.viewButtonFound),
    fpsAboveFloor: samples.every((s) => s.fps >= 30),
    inputMoved: inputDelta > 0.02,
    noPageErrors: errors.length === 0,
    noTemporaryHooks: suspiciousHooks.length === 0,
  }

  const payload = {
    out: OUT,
    canvas,
    samples,
    assetResponses,
    input: { before, after, delta: +inputDelta.toFixed(3) },
    suspiciousHooks,
    errors: errors.slice(0, 8),
    checks,
  }
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(payload, null, 2))
  console.log(JSON.stringify(payload, null, 2))
  await browser.close()
  if (Object.values(checks).some((ok) => !ok)) process.exit(1)
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
