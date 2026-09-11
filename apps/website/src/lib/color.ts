/**
 * Colours the stylesheet owns, handed to code that cannot read CSS: the WebGL scenes, and
 * box-shadow keyframes gsap has to interpolate. The theme is written in oklch and mixed with
 * color-mix, so rather than parse either, let a 1x1 canvas rasterise the colour and read the
 * pixel back as sRGB.
 */
type Rgb = [number, number, number];

let context: CanvasRenderingContext2D | null = null;

function rasterise(value: string): Rgb | null {
  context ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!context || !value) return null;
  const sentinel = "#010203";
  context.fillStyle = sentinel;
  context.fillStyle = value;
  if (context.fillStyle === sentinel && value.toLowerCase() !== sentinel) return null;
  context.clearRect(0, 0, 1, 1);
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return [r, g, b];
}

/** A custom property's colour as it resolves on `element` - so a `.light` section reads its own. */
export function tokenRgb(name: string, element: Element, fallback: Rgb): Rgb {
  return rasterise(getComputedStyle(element).getPropertyValue(name).trim()) ?? fallback;
}

/** What an element actually paints as its background. */
export function backgroundRgb(element: Element, fallback: Rgb): Rgb {
  return rasterise(getComputedStyle(element).backgroundColor) ?? fallback;
}
