import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { backgroundRgb, tokenRgb } from "@/lib/color";
import { toColor, type SceneHandle } from "./use-three-scene";

/**
 * Threads of light, one per kind of source, drifting in from the left with a label riding
 * each head - then, as the section scrolls, fusing into the single highlighted thread.
 *
 * The section's scroll timeline tweens `state`; this only ever reads it.
 */

export type GroundingLine = {
  label: string;
  seed: number;
  amplitude: number;
  positionShift: number;
  highlighted?: boolean;
};

export type GroundingState = {
  /** How far the heads still have to travel in; 12 is off-screen left. */
  enter: number;
  /** 0 = loose threads, 1 = one thread. */
  fuse: number;
  shiftX: number;
  /** The highlighted head's final brightening. */
  highlight: number;
  highlightLabel: number;
  mobile: boolean;
};

export const initialGroundingState = (): GroundingState => ({
  enter: 12,
  fuse: 0,
  shiftX: 0,
  highlight: 0,
  highlightLabel: 1,
  mobile: false
});

// Each thread is evaluated over VALUES steps but drawn through every third one: the wave
// is aliased by that sampling into the long, lazy bends the threads are meant to have.
const VALUES = 100;
const POINTS = 33;
const FOV = 75;
const DISTANCE = 5;

const cube = (x: number) => x * x * x;
const lerp = THREE.MathUtils.lerp;

export function createGroundingScene(
  renderer: THREE.WebGLRenderer,
  container: HTMLElement,
  { lines, state, labels }: { lines: GroundingLine[]; state: GroundingState; labels: (HTMLElement | null)[] }
): SceneHandle {
  const host = container.closest(".data-viz-section") ?? container;
  const scene = new THREE.Scene();
  scene.background = toColor(backgroundRgb(host, [21, 22, 27]));
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
  camera.position.z = DISTANCE;
  const group = new THREE.Group();
  scene.add(group);

  const signal = toColor(tokenRgb("--signal", host, [233, 104, 63]));
  const white = new THREE.Color(0xffffff);
  const threadColor = signal.clone().lerp(white, 0.3);
  const headColor = signal.clone().lerp(white, 0.12);
  const lastColor = signal.clone().lerp(white, 0.55);

  const threads = lines.map((config, index) => {
    const geometry = new LineGeometry();
    geometry.setPositions(new Float32Array(POINTS * 3));
    const material = new LineMaterial({ color: threadColor, linewidth: 0.01, worldUnits: true });
    const line = new Line2(geometry, material);
    line.frustumCulled = false;
    const dot = new THREE.Mesh(
      new THREE.CircleGeometry(0.025, 32),
      new THREE.MeshBasicMaterial({ color: config.highlighted ? headColor : threadColor, transparent: true })
    );
    dot.scale.setScalar(config.highlighted ? 3.5 : 1);
    group.add(line, dot);
    return { config, geometry, material, line, dot, label: labels[index] ?? null, segments: new Float32Array((POINTS - 1) * 6) };
  });

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 1, 0.2, 0.25);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  let width = 1;
  let height = 1;
  let viewWidth = 1; // the frame's width in world units at the threads' depth
  const anchor = new THREE.Vector3();
  const point = [0, 0, 0];

  const sample = (config: GroundingLine, r: number, phase: number, wobble: number) => {
    const { fuse, enter } = state;
    const wave = Math.sin((r - phase) * (1 - 0.002 * enter) * 2);
    const amplitude = lerp(config.amplitude, 0, cube(fuse));
    const base = -0.25 * VALUES + 0.25 * r - enter;
    const loose = base + wobble + config.positionShift;
    const fused = base - (1 - 0.06 * viewWidth);
    const along = lerp(loose, fused, fuse);
    const bend = cube(Math.sin((r / VALUES) * 4 * Math.PI) * Math.sin(2 * config.amplitude) * 1.5) * fuse;
    const acrossValue = bend + wave * amplitude;
    const depth = lerp(0.1 * wave, (1 - fuse) * wave + 0.5, fuse);
    if (state.mobile) {
      point[0] = acrossValue;
      point[1] = -along;
    } else {
      point[0] = along;
      point[1] = acrossValue;
    }
    point[2] = depth;
    return point;
  };

  const update = (time: number) => {
    group.position.x = state.shiftX;
    group.updateMatrixWorld();
    const rest = 1 - state.fuse;

    for (const thread of threads) {
      const { config, segments } = thread;
      const phase = (time + config.seed) * 0.8;
      const wobble = Math.sin(phase + config.seed / 100);

      let px = 0;
      let py = 0;
      let pz = 0;
      for (let k = 0; k < POINTS; k++) {
        const x = sample(config, 3 * k, phase, wobble)[0];
        const y = sample(config, 3 * k + 1, phase, wobble)[1];
        const z = sample(config, 3 * k + 2, phase, wobble)[2];
        if (k > 0) {
          const o = (k - 1) * 6;
          segments[o] = px;
          segments[o + 1] = py;
          segments[o + 2] = pz;
          segments[o + 3] = x;
          segments[o + 4] = y;
          segments[o + 5] = z;
        }
        px = x;
        py = y;
        pz = z;
      }
      const start = thread.geometry.attributes.instanceStart as THREE.InterleavedBufferAttribute;
      (start.data.array as Float32Array).set(segments);
      start.data.needsUpdate = true;

      const hx = sample(config, VALUES - 3, phase, wobble)[0];
      const hy = sample(config, VALUES - 2, phase, wobble)[1];
      const hz = sample(config, VALUES - 1, phase, wobble)[2];
      thread.dot.position.set(hx, hy, hz + (config.highlighted ? 0.008 : 0.001));
      if (config.highlighted) {
        (thread.dot.material as THREE.MeshBasicMaterial).color.copy(headColor).lerp(lastColor, state.highlight);
      }

      const label = thread.label;
      if (label) {
        anchor.set(hx, hy + 0.2 * (config.highlighted ? 1 : rest), hz).applyMatrix4(group.matrixWorld).project(camera);
        const x = (anchor.x * 0.5 + 0.5) * width;
        const y = (0.5 - anchor.y * 0.5) * height;
        label.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -50%)`;
        label.style.opacity = String(config.highlighted ? state.highlightLabel : rest);
      }
    }
  };

  return {
    resize(w, h, pixelRatio) {
      width = w;
      height = h;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      const viewHeight = 2 * DISTANCE * Math.tan(THREE.MathUtils.degToRad(FOV / 2));
      viewWidth = viewHeight * camera.aspect;
      for (const thread of threads) {
        thread.material.resolution.set(w, h);
        if (thread.label) thread.label.style.fontSize = `${((0.1 / viewHeight) * h).toFixed(2)}px`;
      }
      composer.setPixelRatio(pixelRatio);
      composer.setSize(w, h);
      bloom.resolution.set(w, h);
    },
    frame(time) {
      update(time);
      composer.render();
    },
    dispose() {
      for (const thread of threads) {
        thread.geometry.dispose();
        thread.material.dispose();
        thread.dot.geometry.dispose();
        (thread.dot.material as THREE.Material).dispose();
      }
      bloom.dispose();
      composer.dispose();
    }
  };
}
