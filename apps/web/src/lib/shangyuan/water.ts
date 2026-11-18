import * as THREE from 'three'

/**
 * Night river water. Deep navy body, slow ripples, a cold moon specular, and soft
 * vertical streaks standing in for lantern reflections — the thing the eye remembers.
 */
export function createWaterMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uDeep: { value: new THREE.Color('#071026') },
      uShallow: { value: new THREE.Color('#12244a') },
      uMoonDir: { value: new THREE.Vector3(-0.35, 0.75, 0.4).normalize() },
      uLanternX: { value: new Float32Array(12) },
      uLanternI: { value: new Float32Array(12) },
    },
    vertexShader: /* glsl */ `
      varying vec3 vWorld;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vWorld = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform vec3 uDeep;
      uniform vec3 uShallow;
      uniform vec3 uMoonDir;
      uniform float uLanternX[12];
      uniform float uLanternI[12];
      varying vec3 vWorld;

      float wave(vec2 p, float t) {
        return sin(p.x * 0.9 + t * 0.55) * 0.42
             + sin(p.y * 1.6 - t * 0.42) * 0.3
             + sin((p.x * 0.7 + p.y) * 1.1 + t * 0.33) * 0.28;
      }

      void main() {
        vec2 p = vWorld.xz;
        float w = wave(p, uTime);
        float w2 = wave(p * 1.25 + vec2(3.1, 1.7), uTime * 1.15);

        vec3 col = mix(uDeep, uShallow, 0.36 + 0.07 * w);
        col += vec3(0.028, 0.045, 0.08) * (0.5 + 0.5 * w2) * 0.35;

        float streak = 0.0;
        for (int i = 0; i < 12; i++) {
          float x = uLanternX[i];
          if (uLanternI[i] <= 0.001) continue;
          float wob = sin(p.y * 0.8 + uTime * 0.6 + x * 0.7) * 0.45;
          float band = exp(-pow((p.x - x + wob) * 1.9, 2.0));
          float reach = exp(-max(0.0, abs(p.y) - 0.8) * 0.55);
          streak += band * reach * uLanternI[i];
        }
        col += vec3(1.0, 0.5, 0.18) * streak * 0.7;

        vec3 V = normalize(cameraPosition - vWorld);
        vec3 N = normalize(vec3(w * 0.06, 1.0, w2 * 0.06));
        float spec = pow(max(dot(reflect(-uMoonDir, N), V), 0.0), 64.0);
        col += vec3(0.55, 0.7, 1.0) * spec * 0.3;

        float d = length(cameraPosition - vWorld);
        col = mix(col, vec3(0.022, 0.035, 0.07), smoothstep(50.0, 160.0, d));

        gl_FragColor = vec4(col, 1.0);
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
