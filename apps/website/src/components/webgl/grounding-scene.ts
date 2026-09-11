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
 * each head - then, as the section scrolls, drawing together into one point just ahead of
 * the headline.
 *
 * A thread is a single run of points, and its dot and label are placed from that run's last
 * point, so neither can come loose from it. The section's scroll timeline tweens `state`;
 * this only ever reads it.
 */

export type GroundingLine = {
  label: string;
  seed: number;
  amplitude: number;
  positionShift: number;
  /** Where the thread crosses the frame's edge once they have converged: a fraction of the
      frame's height (its width on phones), positive above the focus (right of it on phones). */
  spread: number;
  highlighted?: boolean;
};

export type GroundingState = {
  /** How far the heads still have to travel in; 12 is off-screen left. */
  enter: number;
  /** 0 = loose threads, 1 = drawn together into the focus. */
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

/** How far the group slides left in the last beat, as the headline slides in beside it. */
export const FINAL_SHIFT = 0.5;

const POINTS = 33;
// Points sit 0.75 apart along a thread, but its wave advances three of its own steps per
// point: the undersampling aliases it into the long, lazy bends the threads are meant to
// have, and straightens them as they come in.
const STEP = 0.75;
const FOV = 75;
const DISTANCE = 5;
// Converged, a thread's offset from the focus grows as 1 - e^(-K v^P), v being the distance
// back from the focus over the distance to the frame's edge: the threads arrive tangent and
// tight, and open into a fan toward the edge.
const FAN_K = 1.4;
const FAN_P = 2.28;
const FAN_NORM = 1 - Math.exp(-FAN_K);
// How far ahead of the headline the focus sits, in px.
const FOCUS_GAP = 32;

const lerp = THREE.MathUtils.lerp;
const fan = (v: number) => (1 - Math.exp(-FAN_K * Math.pow(v, FAN_P))) / FAN_NORM;

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
    return {
      config,
      geometry,
      material,
      dot,
      label: labels[index] ?? null,
      points: new Float32Array(POINTS * 3),
      segments: new Float32Array((POINTS - 1) * 6)
    };
  });

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 1, 0.2, 0.25);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  let width = 1;
  let height = 1;
  // The frame's size in world units at the threads' depth.
  let viewWidth = 1;
  let viewHeight = 1;
  let disposed = false;
  // Where the threads meet, in px within the frame: just ahead of the headline's first line,
  // or just above the headline on phones, where it runs along the bottom.
  const focus = { x: 0, y: 0 };
  const anchor = new THREE.Vector3();

  const measure = () => {
    focus.x = width * 0.515;
    focus.y = height * 0.5;
    const block = host.querySelector<HTMLElement>(".data-viz-section__center");
    const title = host.querySelector<HTMLElement>(".data-viz-section__center-title");
    if (!block || !title) return;
    const frame = container.getBoundingClientRect();
    const box = block.getBoundingClientRect();
    const style = getComputedStyle(block);
    if (window.matchMedia("(max-width: 767px)").matches) {
      focus.x = width / 2;
      focus.y = Math.max(height * 0.3, box.top - frame.top - FOCUS_GAP);
    } else {
      const size = parseFloat(getComputedStyle(title).fontSize) || 36;
      focus.x = box.left - frame.left + parseFloat(style.paddingLeft) - FOCUS_GAP;
      // The middle of the headline's first line, which is 1.15 high.
      focus.y = box.top - frame.top + parseFloat(style.paddingTop) + size * 0.575;
    }
  };
  // The headline's box settles once the webfont is in.
  document.fonts?.ready.then(() => {
    if (!disposed) measure();
  });

  const update = (time: number) => {
    group.position.x = state.shiftX;
    group.updateMatrixWorld();
    const { enter, fuse, mobile } = state;
    const rest = 1 - fuse;
    const frequency = 2 * (1 - 0.002 * enter);

    // The focus in world units as the threads see it, before the group's last slide; and how
    // far it is from there back to the edge they come in from.
    const fx = (focus.x / width - 0.5) * viewWidth;
    const fy = (0.5 - focus.y / height) * viewHeight;
    const focusAlong = mobile ? -fy : fx + FINAL_SHIFT;
    const focusAcross = mobile ? fx : fy;
    const reach = Math.max(1, mobile ? viewHeight / 2 - fy : fx + viewWidth / 2);
    const breadth = mobile ? viewWidth : viewHeight;

    for (const thread of threads) {
      const { config, points, segments } = thread;
      const phase = (time + config.seed) * 0.8;
      const wobble = Math.sin(phase + config.seed / 100);
      const spread = config.spread * breadth;

      for (let k = 0; k < POINTS; k++) {
        const back = (POINTS - 1 - k) * STEP;
        const wave = Math.sin((3 * k - phase) * frequency);
        const along = lerp(STEP * k - 25 - enter + wobble + config.positionShift, focusAlong - back, fuse);
        const across = lerp(wave * config.amplitude, focusAcross + spread * fan(back / reach), fuse);
        const o = k * 3;
        points[o] = mobile ? across : along;
        points[o + 1] = mobile ? -along : across;
        points[o + 2] = 0.1 * wave * rest;
      }
      for (let k = 1; k < POINTS; k++) segments.set(points.subarray((k - 1) * 3, (k + 1) * 3), (k - 1) * 6);
      const start = thread.geometry.attributes.instanceStart as THREE.InterleavedBufferAttribute;
      (start.data.array as Float32Array).set(segments);
      start.data.needsUpdate = true;

      // The head is the thread's own last point.
      const head = (POINTS - 1) * 3;
      const hx = points[head];
      const hy = points[head + 1];
      const hz = points[head + 2];
      thread.dot.position.set(hx, hy, hz + (config.highlighted ? 0.008 : 0.001));
      if (config.highlighted) {
        (thread.dot.material as THREE.MeshBasicMaterial).color.copy(headColor).lerp(lastColor, state.highlight);
      }

      const label = thread.label;
      if (label) {
        // Riding just above its head; the others sink onto their dots as they fade.
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
      viewHeight = 2 * DISTANCE * Math.tan(THREE.MathUtils.degToRad(FOV / 2));
      viewWidth = viewHeight * camera.aspect;
      for (const thread of threads) {
        thread.material.resolution.set(w, h);
        if (thread.label) thread.label.style.fontSize = `${((0.1 / viewHeight) * h).toFixed(2)}px`;
      }
      composer.setPixelRatio(pixelRatio);
      composer.setSize(w, h);
      bloom.resolution.set(w, h);
      measure();
    },
    frame(time) {
      update(time);
      composer.render();
    },
    dispose() {
      disposed = true;
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
