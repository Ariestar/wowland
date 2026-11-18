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
      // The reference grade keeps true blacks; a large lift reads as haze.
      uLift: { value: new THREE.Vector3(0.008, 0.006, 0.016) },
      uGain: { value: new THREE.Vector3(1.04, 1.0, 0.97) },
      uSaturation: { value: 1.14 },
      uContrast: { value: 1.1 },
      uVignette: { value: 0.42 },
      uGrain: { value: 0.012 },
      uTime: { value: 0 },
    },
    vertexShader: FULLSCREEN_VERTEX,
    fragmentShader: /* glsl */ `
      uniform sampler2D tDiffuse; uniform vec3 uLift; uniform vec3 uGain;
      uniform float uSaturation; uniform float uContrast; uniform float uVignette;
      uniform float uGrain; uniform float uTime;
      varying vec2 vUv;
      void main() {
        vec3 c = texture2D(tDiffuse, vUv).rgb;
        float l = dot(c, vec3(0.299, 0.587, 0.114));
        c = mix(vec3(l), c, uSaturation);
        c = (c - 0.5) * uContrast + 0.5;
        // Split tone: cool the shadows, warm the lantern-lit highlights.
        float high = smoothstep(0.3, 0.85, l);
        c += mix(vec3(-0.004, 0.002, 0.018), vec3(0.024, 0.008, -0.014), high);
        c = c * uGain + uLift * (1.0 - c);
        float v = smoothstep(0.95, 0.3, length((vUv - 0.5) * vec2(1.25, 1.0)));
        c *= mix(1.0, 0.78 + 0.22 * v, uVignette);
        float n = fract(sin(dot(vUv * vec2(1441.7, 2917.3) + uTime, vec2(12.9898, 78.233))) * 43758.5453);
        c += (n - 0.5) * uGrain;
        gl_FragColor = vec4(max(c, 0.0), 1.0);
      }
    `,
  }
}
