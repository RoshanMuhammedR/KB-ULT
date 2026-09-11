import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { backgroundRgb, tokenRgb } from "@/lib/color";
import { toColor, type SceneHandle } from "./use-three-scene";

/**
 * The hero's glowing wireframe duct: a square-section tube of box frames running in an S
 * through the frame, its ribs flowing along it while the path sways and the section rolls.
 *
 * The glow is the lines drawn three times over - a wide faint halo, a softer body and a thin
 * hot core, added together - rather than a bloom pass, whose widest blur levels would haze
 * the whole square. Everything moves on one period, so the motion loops without a seam.
 */

const LOOP = 8.6;
const FRAME = 6.7; // world units across the square the tube is framed in
const RIBS = 34;
const HALF_SIDE = 0.27;

// The path in fractions of the frame (u right, v down), with depth, sway and phase per point.
// The elbow comes toward the viewer and the ends fall away, so the ducts read in perspective;
// it is rounded over three points and kept clear of the frame's left edge, which would crop
// it to a point.
const PATH = [
  { u: 1.02, v: -0.42, z: -2.6, su: 0.05, sv: 0.02, phase: 0 },
  { u: 0.7, v: -0.02, z: -1.3, su: 0.07, sv: 0.03, phase: 0.7 },
  { u: 0.43, v: 0.19, z: -0.2, su: 0.05, sv: 0.04, phase: 1.4 },
  { u: 0.22, v: 0.37, z: 0.5, su: 0.04, sv: 0.05, phase: 1.9 },
  { u: 0.15, v: 0.47, z: 0.8, su: 0.03, sv: 0.07, phase: 2.3 },
  { u: 0.15, v: 0.57, z: 0.8, su: 0.03, sv: 0.07, phase: 2.6 },
  { u: 0.23, v: 0.67, z: 0.5, su: 0.04, sv: 0.05, phase: 3 },
  { u: 0.47, v: 0.8, z: -0.2, su: 0.06, sv: 0.03, phase: 3.6 },
  { u: 0.71, v: 0.98, z: -1.3, su: 0.07, sv: 0.02, phase: 4.4 },
  { u: 0.95, v: 1.42, z: -2.8, su: 0.05, sv: 0.02, phase: 5.2 }
];

// Per segment: its four ring edges; per span between rings: four rails and two braces.
const SEGMENTS = RIBS * 4 + (RIBS - 1) * 6;
const LAYERS = [
  { width: 9, opacity: 0.1 },
  { width: 4, opacity: 0.3 },
  { width: 1.4, opacity: 1 }
];

export function createHeroTube(renderer: THREE.WebGLRenderer, container: HTMLElement): SceneHandle {
  const host = container.closest(".main-hero") ?? container;
  const scene = new THREE.Scene();
  scene.background = toColor(backgroundRgb(host, [14, 15, 18]));
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
  camera.position.set(0, 0, 11);

  const points = PATH.map(() => new THREE.Vector3());
  const curve = new THREE.CatmullRomCurve3(points, false, "centripetal");

  const positions = new Float32Array(SEGMENTS * 6);
  const colors = new Float32Array(SEGMENTS * 6);
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(positions);
  geometry.setColors(colors);
  const materials = LAYERS.map(
    (layer) =>
      new LineMaterial({
        color: 0xffffff,
        vertexColors: true,
        linewidth: layer.width,
        worldUnits: false,
        transparent: true,
        opacity: layer.opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false
      })
  );
  for (const material of materials) {
    const lines = new LineSegments2(geometry, material);
    lines.frustumCulled = false;
    scene.add(lines);
  }

  // The layers add up toward white where they overlap; start the core only slightly lifted.
  const signal = toColor(tokenRgb("--signal", host, [233, 104, 63]));
  const core = signal.clone().lerp(new THREE.Color(0xffffff), 0.06);

  const corners = Array.from({ length: RIBS }, () => Array.from({ length: 4 }, () => new THREE.Vector3()));
  const tangent = new THREE.Vector3();
  const across = new THREE.Vector3();
  const toward = new THREE.Vector3();
  const view = new THREE.Vector3(0, 0, 1);
  const centre = new THREE.Vector3();

  const place = (time: number) => {
    const omega = (Math.PI * 2) / LOOP;
    PATH.forEach((p, i) => {
      const u = p.u + p.su * Math.sin(omega * time + p.phase);
      const v = p.v + p.sv * Math.sin(omega * time + p.phase * 1.3);
      points[i].set((u - 0.5) * FRAME, (0.5 - v) * FRAME, p.z);
    });
    curve.updateArcLengths();

    const flow = ((time / LOOP) * 2) % 1;
    for (let k = 0; k < RIBS; k++) {
      const at = (k + flow) / RIBS;
      curve.getPointAt(at, centre);
      curve.getTangentAt(at, tangent);
      // A frame that keeps a corner toward the viewer - so two faces show - rolled a little
      // by a wave running down the tube.
      toward.copy(view).addScaledVector(tangent, -view.dot(tangent)).normalize();
      across.crossVectors(toward, tangent).normalize();
      const roll = 0.35 * Math.sin(Math.PI * 2 * (at * 1.2 - time / LOOP));
      for (let j = 0; j < 4; j++) {
        const angle = roll + (j * Math.PI) / 2;
        corners[k][j]
          .copy(centre)
          .addScaledVector(across, Math.cos(angle) * HALF_SIDE * Math.SQRT2)
          .addScaledVector(toward, Math.sin(angle) * HALF_SIDE * Math.SQRT2);
      }
    }
  };

  let cursor = 0;
  const vertex = (point: THREE.Vector3, strength: number) => {
    // Edges further back dim, so each frame reads as a box rather than a flat pattern.
    const depth = THREE.MathUtils.clamp((point.z + 3) / 4.5, 0, 1);
    const k = strength * (0.3 + 0.7 * depth);
    colors[cursor] = core.r * k;
    colors[cursor + 1] = core.g * k;
    colors[cursor + 2] = core.b * k;
    positions[cursor] = point.x;
    positions[cursor + 1] = point.y;
    positions[cursor + 2] = point.z;
    cursor += 3;
  };
  const segment = (a: THREE.Vector3, b: THREE.Vector3, strength = 1) => {
    vertex(a, strength);
    vertex(b, strength);
  };

  const build = () => {
    cursor = 0;
    for (let k = 0; k < RIBS; k++) {
      const ring = corners[k];
      for (let j = 0; j < 4; j++) segment(ring[j], ring[(j + 1) % 4]);
      if (k === RIBS - 1) continue;
      const next = corners[k + 1];
      for (let j = 0; j < 4; j++) segment(ring[j], next[j]);
      // A brace across two opposite faces; seen through the frame they cross into an X.
      segment(ring[0], next[1], 0.75);
      segment(ring[2], next[3], 0.75);
    }
    const start = geometry.attributes.instanceStart as THREE.InterleavedBufferAttribute;
    const colour = geometry.attributes.instanceColorStart as THREE.InterleavedBufferAttribute;
    (start.data.array as Float32Array).set(positions);
    (colour.data.array as Float32Array).set(colors);
    start.data.needsUpdate = true;
    colour.data.needsUpdate = true;
  };

  return {
    resize(width, height) {
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      for (const material of materials) material.resolution.set(width, height);
    },
    frame(time) {
      place(time);
      build();
      renderer.render(scene, camera);
    },
    dispose() {
      geometry.dispose();
      for (const material of materials) material.dispose();
    }
  };
}
