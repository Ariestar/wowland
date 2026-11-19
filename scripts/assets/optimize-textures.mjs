/**
 * Re-encode the GLB's PNG textures as WebP and rewrite the container.
 *
 * The foliage atlases and roughness maps are the bulk of the download.  WebP
 * keeps the alpha channel and cuts those images by roughly three quarters, and
 * three's GLTFLoader reads them through EXT_texture_webp.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))

export function optimizeTextures(glbPath, { quality = 90 } = {}) {
  const file = fs.readFileSync(glbPath)
  const jsonLength = file.readUInt32LE(12)
  const json = JSON.parse(file.subarray(20, 20 + jsonLength).toString('utf8'))
  const binLength = file.readUInt32LE(20 + jsonLength)
  const binStart = 28 + jsonLength
  const bin = file.subarray(binStart, binStart + binLength)

  const imagesByView = new Map()
  for (const [index, image] of (json.images ?? []).entries()) {
    if (image.bufferView === undefined) continue
    if (!imagesByView.has(image.bufferView)) imagesByView.set(image.bufferView, [])
    imagesByView.get(image.bufferView).push(index)
  }

  const jobs = []
  for (const [viewIndex, imageIndexes] of imagesByView) {
    const image = json.images[imageIndexes[0]]
    if (image.mimeType !== 'image/png') continue
    const view = json.bufferViews[viewIndex]
    const start = view.byteOffset ?? 0
    jobs.push({
      viewIndex,
      imageIndexes,
      input: { bytes: bin.subarray(start, start + view.byteLength) },
    })
  }

  if (jobs.length === 0) {
    console.log('LR_WEBP_SKIP no png textures')
    return { saved: 0, images: 0 }
  }

  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'lw-webp-'))
  const manifest = []
  for (const [index, job] of jobs.entries()) {
    job.inputPath = path.join(temp, `in-${index}.png`)
    job.outputPath = path.join(temp, `out-${index}.webp`)
    fs.writeFileSync(job.inputPath, job.input.bytes)
    manifest.push({ input: job.inputPath, output: job.outputPath })
    delete job.input
  }
  const manifestPath = path.join(temp, 'jobs.json')
  fs.writeFileSync(manifestPath, JSON.stringify(manifest))

  const encode = spawnSync('python', [path.join(HERE, 'webp_encode.py'), manifestPath, String(quality)], {
    stdio: 'inherit',
  })
  if (encode.error) throw encode.error
  if (encode.status !== 0) throw new Error(`webp_encode.py exited ${encode.status}`)

  const replacements = new Map()
  for (const job of jobs) {
    const bytes = fs.readFileSync(job.outputPath)
    replacements.set(job.viewIndex, bytes)
    for (const imageIndex of job.imageIndexes) json.images[imageIndex].mimeType = 'image/webp'
  }

  const chunks = []
  let offset = 0
  for (const [index, view] of json.bufferViews.entries()) {
    const start = view.byteOffset ?? 0
    const original = bin.subarray(start, start + view.byteLength)
    const data = replacements.get(index) ?? original
    while (offset % 4 !== 0) {
      chunks.push(Buffer.from([0]))
      offset += 1
    }
    view.byteOffset = offset
    view.byteLength = data.length
    chunks.push(data)
    offset += data.length
  }
  const nextBin = Buffer.concat(chunks)
  json.buffers[0].byteLength = nextBin.length

  for (const texture of json.textures ?? []) {
    if (texture.source === undefined) continue
    if (json.images[texture.source]?.mimeType !== 'image/webp') continue
    texture.extensions = {
      ...(texture.extensions ?? {}),
      EXT_texture_webp: { source: texture.source },
    }
  }
  json.extensionsUsed = [...new Set([...(json.extensionsUsed ?? []), 'EXT_texture_webp'])]

  const jsonText = JSON.stringify(json)
  const jsonBuffer = Buffer.from(jsonText + ' '.repeat((4 - (jsonText.length % 4)) % 4))
  const binBuffer = Buffer.concat([nextBin, Buffer.alloc((4 - (nextBin.length % 4)) % 4)])

  const header = Buffer.alloc(12)
  header.writeUInt32LE(0x46546c67, 0)
  header.writeUInt32LE(2, 4)
  header.writeUInt32LE(12 + 8 + jsonBuffer.length + 8 + binBuffer.length, 8)
  const jsonHeader = Buffer.alloc(8)
  jsonHeader.writeUInt32LE(jsonBuffer.length, 0)
  jsonHeader.writeUInt32LE(0x4e4f534a, 4)
  const binHeader = Buffer.alloc(8)
  binHeader.writeUInt32LE(binBuffer.length, 0)
  binHeader.writeUInt32LE(0x004e4942, 4)

  fs.writeFileSync(glbPath, Buffer.concat([header, jsonHeader, jsonBuffer, binHeader, binBuffer]))
  fs.rmSync(temp, { recursive: true, force: true })

  const saved = file.length - fs.statSync(glbPath).size
  console.log(`LR_WEBP_OK ${jobs.length} images, ${(saved / 1024 / 1024).toFixed(2)} MB saved`)
  return { saved, images: jobs.length }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = process.argv[2]
  if (!target) {
    console.error('usage: node scripts/assets/optimize-textures.mjs <world.glb>')
    process.exit(1)
  }
  optimizeTextures(target)
}
