import * as THREE from "three";
import { tokenRgb } from "@/lib/color";
import type { SceneHandle } from "./use-three-scene";

/**
 * The floor under the footer: a grid on a plane seen from just above it, drifting toward the
 * viewer, fading to the sides and into the distance, and glowing a little brighter wherever
 * the pointer hovers over it.
 */

const vertexShader = /* glsl */ `
  void main() {
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  precision highp float;

  uniform vec2 uResolution;
  uniform float uPixelRatio;
  uniform float uTime;
  uniform float uCell;
  uniform vec2 uPointer;
  uniform float uPointerStrength;
  uniform vec3 uGround;
  uniform vec3 uLine;

  const float FOV = 0.62;    // tangent of half the vertical field of view
  const float PITCH = 0.15;  // how far the view tips below level; puts the horizon above centre
  const float EYE = 1.0;     // height above the floor

  // Where a pixel's ray meets the floor: (x, depth) plus the distance travelled.
  vec3 floorAt(vec2 ndc, float aspect) {
    vec3 ray = normalize(vec3(ndc.x * aspect * FOV, ndc.y * FOV - PITCH, 1.0));
    float t = EYE / max(-ray.y, 1e-4);
    return vec3(ray.x * t, ray.z * t, t);
  }

  float gridLines(vec2 p, float width) {
    vec2 d = abs(fract(p + 0.5) - 0.5);
    vec2 aa = fwidth(p) * 1.25;
    vec2 line = 1.0 - smoothstep(vec2(width), vec2(width) + aa, d);
    return max(line.x, line.y);
  }

  float halo(vec2 p, float radius) {
    vec2 d = abs(fract(p + 0.5) - 0.5);
    return 1.0 - smoothstep(0.0, radius, min(d.x, d.y));
  }

  void main() {
    vec2 ndc = (gl_FragCoord.xy / uPixelRatio) / uResolution * 2.0 - 1.0;
    float aspect = uResolution.x / uResolution.y;

    vec3 hit = floorAt(ndc, aspect);
    vec2 cell = hit.xy / uCell;
    cell.y += uTime;
    vec3 pointerHit = floorAt(uPointer * 2.0 - 1.0, aspect);
    vec2 pointerCell = pointerHit.xy / uCell;
    pointerCell.y += uTime;

    float belowHorizon = smoothstep(0.0, 0.1, PITCH - ndc.y * FOV);
    float far = 1.0 - smoothstep(5.0, 20.0, hit.z);
    float sides = 1.0 - smoothstep(0.5, 1.0, abs(ndc.x));
    float fade = belowHorizon * far * sides * 0.8;

    float near = (1.0 - smoothstep(0.0, 2.5, distance(cell, pointerCell))) * uPointerStrength;
    float line = gridLines(cell, 0.012) * fade;
    float glow = halo(cell, 0.05) * fade;

    vec3 color = uGround + uLine * glow * (0.12 + 0.5 * near);
    color = mix(color, uLine * (0.62 + 0.5 * near), line);
    gl_FragColor = vec4(color, 1.0);
  }
`;

export type FooterGridParams = { cell: number };

export function createFooterGrid(
  renderer: THREE.WebGLRenderer,
  container: HTMLElement,
  params: FooterGridParams
): SceneHandle {
  const scene = new THREE.Scene();
  const camera = new THREE.Camera();
  // The shader writes final colours itself, so it is handed display (sRGB) values, untouched.
  const srgb = ([r, g, b]: [number, number, number], scale = 1) => new THREE.Color((r / 255) * scale, (g / 255) * scale, (b / 255) * scale);
  const ground = srgb(tokenRgb("--surface-raised", container, [30, 31, 38]));
  const line = srgb(tokenRgb("--signal", container, [233, 104, 63]), 0.5);

  const uniforms = {
    uResolution: { value: new THREE.Vector2(1, 1) },
    uPixelRatio: { value: 1 },
    uTime: { value: 0 },
    uCell: { value: params.cell },
    uPointer: { value: new THREE.Vector2(0.5, 0.35) },
    uPointerStrength: { value: 0 },
    uGround: { value: ground },
    uLine: { value: line }
  };
  const material = new THREE.ShaderMaterial({ vertexShader, fragmentShader, uniforms, depthTest: false, depthWrite: false });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  quad.frustumCulled = false;
  scene.add(quad);

  const target = new THREE.Vector2(0.5, 0.35);
  let movedAt = -Infinity;
  const onMove = (x: number, y: number) => {
    target.set(THREE.MathUtils.clamp(x / window.innerWidth, 0, 1), THREE.MathUtils.clamp(1 - y / window.innerHeight, 0, 1));
    movedAt = performance.now();
  };
  const onPointer = (event: PointerEvent) => onMove(event.clientX, event.clientY);
  window.addEventListener("pointermove", onPointer);

  return {
    resize(width, height, pixelRatio) {
      uniforms.uResolution.value.set(width, height);
      uniforms.uPixelRatio.value = pixelRatio;
    },
    frame(_time, delta) {
      const moving = performance.now() - movedAt < 60 ? 1 : 0;
      uniforms.uPointerStrength.value = THREE.MathUtils.lerp(uniforms.uPointerStrength.value, moving, 1 - Math.exp(-delta));
      uniforms.uPointer.value.lerp(target, 0.05);
      uniforms.uTime.value += 0.5 * delta;
      uniforms.uCell.value = params.cell;
      renderer.render(scene, camera);
    },
    dispose() {
      window.removeEventListener("pointermove", onPointer);
      quad.geometry.dispose();
      material.dispose();
    }
  };
}
