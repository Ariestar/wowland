import * as THREE from 'three'

const COUNT = 720
const SPAN_X = 64
const SPAN_Z = 116
const FALL_HEIGHT = 24

const VERTEX_SHADER = /* glsl */ `
  attribute float aPhase;
  attribute float aSpeed;
  attribute float aSize;

  uniform float uTime;
  uniform vec3 uPlayer;

  varying float vFade;

  void main() {
    vec3 p = position;
    p.x = uPlayer.x + mod(p.x - uPlayer.x + ${SPAN_X.toFixed(1)} * 0.5, ${SPAN_X.toFixed(1)}) - ${SPAN_X.toFixed(1)} * 0.5;
    p.z = uPlayer.z + mod(p.z - uPlayer.z + ${SPAN_Z.toFixed(1)} * 0.5, ${SPAN_Z.toFixed(1)}) - ${SPAN_Z.toFixed(1)} * 0.5;
    float fall = mod(p.y - uTime * aSpeed, ${FALL_HEIGHT.toFixed(1)});
    p.y = 1.2 + fall;
    p.x += sin(uTime * 0.62 + aPhase) * 1.6;
    p.z += cos(uTime * 0.41 + aPhase * 1.7) * 1.2;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = aSize * (300.0 / max(1.0, -mv.z));
    vFade = smoothstep(0.0, 2.5, fall) * (1.0 - smoothstep(18.0, ${FALL_HEIGHT.toFixed(1)}, fall));
  }
`

const FRAGMENT_SHADER = /* glsl */ `
  uniform sampler2D uMap;
  varying float vFade;

  void main() {
    vec2 uv = gl_PointCoord - vec2(0.5);
    float radius = length(uv);
    float petal = smoothstep(0.5, 0.12, radius);
    if (petal <= 0.01) discard;
    vec3 tint = texture2D(uMap, gl_PointCoord).rgb;
    gl_FragColor = vec4(tint * vec3(1.0, 0.74, 0.86), petal * vFade * 0.82);
  }
`

/** One draw call of player-centred blossom fall, textured from the public kit. */
export class AmbientPetals {
  readonly object: THREE.Points

  private readonly geometry: THREE.BufferGeometry
  private readonly material: THREE.ShaderMaterial
  private readonly texture: THREE.Texture

  constructor(texture: THREE.Texture) {
    this.texture = texture
    texture.colorSpace = THREE.SRGBColorSpace
    texture.wrapS = THREE.RepeatWrapping
    texture.wrapT = THREE.RepeatWrapping

    const positions = new Float32Array(COUNT * 3)
    const phases = new Float32Array(COUNT)
    const speeds = new Float32Array(COUNT)
    const sizes = new Float32Array(COUNT)
    let seed = 0x5eed1234
    const random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
      return seed / 0x1_0000_0000
    }

    for (let i = 0; i < COUNT; i++) {
      positions[i * 3] = (random() - 0.5) * SPAN_X
      positions[i * 3 + 1] = random() * FALL_HEIGHT
      positions[i * 3 + 2] = (random() - 0.5) * SPAN_Z
      phases[i] = random() * Math.PI * 2
      speeds[i] = 0.6 + random() * 1.35
      sizes[i] = 0.22 + random() * 0.24
    }

    this.geometry = new THREE.BufferGeometry()
    this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    this.geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1))
    this.geometry.setAttribute('aSpeed', new THREE.BufferAttribute(speeds, 1))
    this.geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1))

    this.material = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      uniforms: {
        uTime: { value: 0 },
        uPlayer: { value: new THREE.Vector3() },
        uMap: { value: texture },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
    })

    this.object = new THREE.Points(this.geometry, this.material)
    this.object.name = 'AmbientPetals'
    this.object.frustumCulled = false
    this.object.renderOrder = 3
    this.object.userData.noGtao = true
  }

  update(player: THREE.Vector3, time: number) {
    this.material.uniforms.uTime.value = time
    ;(this.material.uniforms.uPlayer.value as THREE.Vector3).copy(player)
  }

  dispose() {
    this.geometry.dispose()
    this.material.dispose()
    this.texture.dispose()
  }
}
