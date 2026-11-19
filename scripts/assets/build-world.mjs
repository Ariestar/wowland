#!/usr/bin/env node
/**
 * Rebuild the Lantern River level and publish it to the web app.
 *
 * Steps: foliage atlases (optional) -> Blender scene -> GLB + layout export ->
 * copy into apps/web/public.  Every step is the same command a person would run
 * by hand, so a failure points at one script rather than a hidden wrapper.
 *
 *   node scripts/assets/build-world.mjs --atlas     # full rebuild
 *   node scripts/assets/build-world.mjs             # scene + export only
 *   node scripts/assets/build-world.mjs --export    # export the saved scene
 */
import { spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const assetDir = join(root, 'packages', 'assets', 'lantern-river')
const scripts = join(assetDir, 'scripts')
const blend = join(assetDir, 'exports', 'SM_Scene_LanternRiver_Night.blend')
const publicDir = join(root, 'apps', 'web', 'public', 'models', 'lantern-river')

const args = new Set(process.argv.slice(2))
const withAtlas = args.has('--atlas')
const exportOnly = args.has('--export')
const noCopy = args.has('--no-copy')

const blender =
  process.env.BLENDER ||
  (existsSync('D:\\Workspace\\Apps\\Scoop\\shims\\blender.exe')
    ? 'D:\\Workspace\\Apps\\Scoop\\shims\\blender.exe'
    : 'blender')

function run(label, command, commandArgs, env = {}) {
  process.stdout.write(`\n▸ ${label}\n`)
  const result = spawnSync(command, commandArgs, {
    cwd: assetDir,
    stdio: 'inherit',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', ...env },
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`${label} exited with ${result.status}`)
  }
}

function sizeMb(path) {
  return (statSync(path).size / 1e6).toFixed(2)
}

/** Read the JSON chunk of a GLB so the build can assert on what it shipped. */
function readGlbJson(path) {
  const data = readFileSync(path)
  const length = data.readUInt32LE(12)
  return JSON.parse(data.subarray(20, 20 + length).toString('utf8'))
}

if (withAtlas) {
  run('foliage atlases', blender, ['-b', '--python-exit-code', '1', '--python', join(scripts, 'make_foliage_atlas.py')])
}

if (!exportOnly) {
  run('blender scene', blender, ['-b', '--python-exit-code', '1', '--python', join(scripts, 'build_scene.py')], {
    LR_SKIP_RENDER: '1',
  })
}

run('glb + layout export', blender, [
  '-b',
  blend,
  '--python-exit-code',
  '1',
  '--python',
  join(scripts, 'export_web_world.py'),
  '--',
  '--out',
  join(assetDir, 'web', 'world.glb'),
  '--layout',
  join(assetDir, 'web', 'layout.json'),
  '--draco',
])

const glb = join(assetDir, 'web', 'world.glb')
const layout = join(assetDir, 'web', 'layout.json')
const doc = readGlbJson(glb)
const masked = doc.materials.filter((m) => m.alphaMode === 'MASK').length
if (masked < 2) {
  throw new Error(`expected foliage cards to export as alphaMode MASK, got ${masked}`)
}

if (!noCopy) {
  copyFileSync(glb, join(publicDir, 'world.glb'))
  copyFileSync(layout, join(publicDir, 'layout.json'))
}

process.stdout.write(
  `\n✓ world.glb ${sizeMb(glb)} MB · layout.json ${sizeMb(layout)} MB · ` +
    `${doc.meshes.length} meshes · ${doc.materials.length} materials · ${masked} masked\n`,
)
