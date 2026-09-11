"use client";

import { useEffect, useRef } from "react";

let tile: string | null = null;

/** One tile of grayscale noise, generated once per visit instead of shipped as an asset. */
function noiseTile() {
  if (tile) return tile;
  const size = 192;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return "";
  const image = context.createImageData(size, size);
  for (let i = 0; i < image.data.length; i += 4) {
    const value = (Math.random() * 255) | 0;
    image.data[i] = value;
    image.data[i + 1] = value;
    image.data[i + 2] = value;
    image.data[i + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  tile = canvas.toDataURL("image/png");
  return tile;
}

/** Film grain over the whole page. The tile jumps between offsets, so the grain crawls. */
export function Noise() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.backgroundImage = `url(${noiseTile()})`;
    element.style.opacity = "0.05";
  }, []);

  return <div ref={ref} className="noise" aria-hidden="true" />;
}
