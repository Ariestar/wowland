import * as THREE from 'three'

/*
 * Grading after tone mapping: a touch of tint in the shadows, warmth in the
 * highlights, saturation and a faint vignette. Kept light so the image stays crisp.
 */

const FULLSCREEN_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`

/**
 * Runs before bloom. A single NaN or infinite pixel is harmless on its own, but bloom's blur
 * spreads it over the whole frame, which shows as a black flash; drop such pixels and cap the
 * rest well inside half-float range.
 */
export function sanitizeShader() {
  return {
    uniforms: { tDiffuse: { value: null as THREE.Texture | null } },
    vertexShader: FULLSCREEN_VERTEX,
    fragmentShader: /* glsl */ `
      uniform sampler2D tDiffuse;
      varying vec2 vUv;
      void main() {
        vec4 c = texture2D(tDiffuse, vUv);
        // comparisons with NaN are always false, and unlike isnan() they survive D3D's fast-math
        float sum = c.r + c.g + c.b;
        bool bad = !(sum < 1e6 && sum > -1e6);
        gl_FragColor = vec4(bad ? vec3(0.0) : clamp(c.rgb, 0.0, 48.0), 1.0);
      }
    `,
  }
}

export function gradingShader() {
  return {
    uniforms: {
      tDiffuse: { value: null as THREE.Texture | null },
      uLift: { value: new THREE.Vector3(0.04, 0.02, 0.07) },
      uGain: { value: new THREE.Vector3(1, 1, 1) },
      uSaturation: { value: 0.9 },
      uVignette: { value: 0.15 },
    },
    vertexShader: FULLSCREEN_VERTEX,
    fragmentShader: /* glsl */ `
      uniform sampler2D tDiffuse; uniform vec3 uLift; uniform vec3 uGain; uniform float uSaturation; uniform float uVignette;
      varying vec2 vUv;
      void main() {
        vec3 c = texture2D(tDiffuse, vUv).rgb;
        float l = dot(c, vec3(0.299, 0.587, 0.114));
        c = mix(vec3(l), c, uSaturation);
        c = c * uGain + uLift * (1.0 - c);
        float v = smoothstep(0.95, 0.3, length((vUv - 0.5) * vec2(1.25, 1.0)));
        c *= mix(1.0, 0.82 + 0.18 * v, uVignette);
        gl_FragColor = vec4(c, 1.0);
      }
    `,
  }
}
