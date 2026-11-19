import * as THREE from 'three'

/**
 * Night river water.
 *
 * The palette and the layered structure follow the reference lantern-river
 * build: ink-dark body, a cool horizon sheen, warm amber banks, and long
 * vertical smears under every lantern.  The surface is slightly transparent so
 * the mirrored world below it supplies the facades and bridge reflections.
 */
export function createWaterMaterial(surfaceAlpha = 0.8) {
  return new THREE.ShaderMaterial({
    transparent: true,
    uniforms: {
      uTime: { value: 0 },
      uSurfaceAlpha: { value: surfaceAlpha },
      /** Half-resolution planar reflection rendered from a mirrored camera. */
      uReflection: { value: null as THREE.Texture | null },
      uReflectionStrength: { value: 0 },
      uReflectionMatrix: { value: new THREE.Matrix4() },
      /** Bank line from layout.json, so the glow follows the canal width. */
      uBankX: { value: 12.5 },
      uDeep: { value: new THREE.Color('#020a18') },
      uShallow: { value: new THREE.Color('#0a1b33') },
      uHorizon: { value: new THREE.Color('#1b2d52') },
      uMoonDir: { value: new THREE.Vector3(-0.35, 0.75, 0.4).normalize() },
      uLanternX: { value: new Float32Array(12) },
      uLanternZ: { value: new Float32Array(12) },
      uLanternI: { value: new Float32Array(12) },
    },
    vertexShader: /* glsl */ `
      uniform float uTime;
      uniform mat4 uReflectionMatrix;
      varying vec3 vWorld;
      varying vec4 vReflectionUv;
      float wave(vec2 p, float t) {
        return sin(p.x * 0.9 + t * 0.55) * 0.42
             + sin(p.y * 1.6 - t * 0.42) * 0.3
             + sin((p.x * 0.7 + p.y) * 1.1 + t * 0.33) * 0.28;
      }
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        // A small vertical swell gives the surface real silhouette against the
        // lantern light instead of a perfectly flat plane.
        wp.y += wave(wp.xz, uTime) * 0.035;
        vWorld = wp.xyz;
        vReflectionUv = uReflectionMatrix * vec4(wp.xyz, 1.0);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uSurfaceAlpha;
      uniform float uBankX;
      uniform vec3 uDeep;
      uniform vec3 uShallow;
      uniform vec3 uHorizon;
      uniform vec3 uMoonDir;
      uniform sampler2D uReflection;
      uniform float uReflectionStrength;
      uniform float uLanternX[12];
      uniform float uLanternZ[12];
      uniform float uLanternI[12];
      varying vec3 vWorld;
      varying vec4 vReflectionUv;

      float wave(vec2 p, float t) {
        return sin(p.x * 0.9 + t * 0.55) * 0.42
             + sin(p.y * 1.6 - t * 0.42) * 0.3
             + sin((p.x * 0.7 + p.y) * 1.1 + t * 0.33) * 0.28;
      }

      void main() {
        vec2 p = vWorld.xz;
        float w = wave(p, uTime);
        float w2 = wave(p * 1.25 + vec2(3.1, 1.7), uTime * 1.15);

        // Body colour: deep ink in the middle, lifting toward both banks.
        float bankMix = smoothstep(2.0, uBankX, abs(p.x));
        vec3 col = mix(uDeep, uShallow, 0.28 + 0.10 * w);
        col = mix(col, uShallow * 1.25, bankMix * 0.22);

        // Warm spill from the quay lanterns, broken into long streaks.
        float bank = exp(-pow((abs(p.x) - uBankX) / 4.6, 2.0));
        col += vec3(0.155, 0.058, 0.018) * bank * (0.22 + 0.08 * w2);
        float edge = exp(-pow((abs(p.x) - uBankX) / 2.9, 2.0));
        float glint = pow(0.5 + 0.5 * sin(p.y * 0.85 + sin(p.y * 0.29) * 2.6 + uTime * 0.28), 9.0);
        col += vec3(0.52, 0.21, 0.06) * edge * glint * 0.3;

        // Lantern pools.  Each one stretches downriver rather than reading as
        // a floating dot, matching the reference's painted reflections.
        float streak = 0.0;
        for (int i = 0; i < 12; i++) {
          if (uLanternI[i] <= 0.001) continue;
          vec2 d = p - vec2(uLanternX[i], uLanternZ[i]);
          d.x += sin(d.y * 1.4 + uTime * 0.6) * 0.12;
          float pool = exp(-dot(d * vec2(1.25, 0.34), d * vec2(1.25, 0.34)) * 1.2);
          streak += pool * uLanternI[i];
        }
        col += vec3(1.0, 0.48, 0.16) * streak * 0.95;

        // The tower island's reflection is the strongest warm anchor on the river.
        float towerPool = exp(-pow(p.x * 0.30, 2.0)) * exp(-abs(p.y + 78.0) * 0.085);
        col += vec3(1.0, 0.46, 0.16) * towerPool * 0.34;
        // A broad amber wash under the bridge deck.
        float bridgePool = exp(-pow((p.y - 10.0) / 7.0, 2.0)) * exp(-pow(p.x * 0.22, 2.0));
        col += vec3(0.35, 0.13, 0.04) * bridgePool * 0.16;

        // Cool sky reflection at grazing angles.
        vec3 V = normalize(cameraPosition - vWorld);
        float fresnel = pow(1.0 - max(V.y, 0.0), 4.0);
        col = mix(col, uHorizon, fresnel * 0.34);

        // Planar reflection from the mirrored camera.  Wave offsets break the
        // mirror into streaks instead of a hard copy of the facades.
        if (uReflectionStrength > 0.001) {
          vec2 ruv = vReflectionUv.xy / vReflectionUv.w;
          ruv += vec2(w, w2) * 0.0006;
          vec3 refl = texture2D(uReflection, ruv).rgb;
          // Add the mirror on top of the painted streaks; replacing them made
          // the far canal read as flat blue.
          col += refl * vec3(1.08, 0.98, 0.9) * uReflectionStrength * (0.18 + 0.30 * fresnel);
        }

        // Moon glitter: a narrow, broken path rather than a mirror disc.
        vec3 N = normalize(vec3(w * 0.06, 1.0, w2 * 0.06));
        float spec = pow(max(dot(reflect(-uMoonDir, N), V), 0.0), 72.0);
        float moonRoad = exp(-pow((p.x + p.y * 0.06) * 0.10, 2.0));
        col += vec3(0.55, 0.68, 1.0) * spec * 0.30 * moonRoad;

        float d = length(cameraPosition - vWorld);
        col = mix(col, uHorizon * 0.55, smoothstep(70.0, 210.0, d));

        gl_FragColor = vec4(col, uSurfaceAlpha);
      }
    `,
  })
}

/** Soft round gradient used for lantern halos, glows and reflection sprites. */
export function glowTexture() {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255,238,205,1)')
  g.addColorStop(0.3, 'rgba(255,196,110,0.55)')
  g.addColorStop(1, 'rgba(255,160,60,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** Soft paper-lantern body for the sky lanterns: warm core, feathered edge. */
export function skyLanternTexture() {
  const w = 96
  const h = 128
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')!
  ctx.save()
  ctx.translate(w / 2, h / 2)
  ctx.scale(w / h, 1)
  const g = ctx.createRadialGradient(0, 0, 2, 0, 0, h / 2)
  g.addColorStop(0, 'rgba(255,248,224,1)')
  g.addColorStop(0.28, 'rgba(255,214,150,0.95)')
  g.addColorStop(0.58, 'rgba(255,162,78,0.45)')
  g.addColorStop(1, 'rgba(255,130,48,0)')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(0, 0, h / 2, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** A soft bat silhouette for the dusk flock above the canal. */
export function batTexture() {
  const w = 128
  const h = 64
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = 'rgba(4,6,14,0.95)'
  ctx.beginPath()
  ctx.ellipse(w / 2, h / 2, 7, 12, 0, 0, Math.PI * 2)
  ctx.fill()
  for (const s of [-1, 1]) {
    ctx.beginPath()
    ctx.moveTo(w / 2, h / 2 - 2)
    ctx.quadraticCurveTo(w / 2 + s * 26, h / 2 - 22, w / 2 + s * 58, h / 2 - 5)
    ctx.quadraticCurveTo(w / 2 + s * 42, h / 2 + 3, w / 2 + s * 30, h / 2 + 1)
    ctx.quadraticCurveTo(w / 2 + s * 18, h / 2 + 12, w / 2 + s * 8, h / 2 + 8)
    ctx.closePath()
    ctx.fill()
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}
