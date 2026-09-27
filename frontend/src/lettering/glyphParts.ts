// Slovo naslova sastavljeno od delova slova originala (Faza 6b), kao u Photoshopu: izrez iz
// jednog slova, pa pomeranje, veličina, rotacija i ogledalo na platnu novog slova.

import type { GlyphPart, TitleGlyph, TitleGlyphs } from "../api";

export interface Point {
  x: number;
  y: number;
}

/** Platno novog slova, u pikselima slova originala: osnovna linija i visina velikog slova. */
export interface GlyphCanvas {
  width: number;
  height: number;
  baseline: number;
  capLine: number;
}

export function glyphCanvas(title: TitleGlyphs): GlyphCanvas {
  const cap = title.cap_height;
  return { width: Math.round(cap * 2.2), height: Math.round(cap * 1.8), baseline: Math.round(cap * 1.45), capLine: Math.round(cap * 0.45) };
}

export function rectPolygon(a: Point, b: Point): number[][] {
  const [x0, x1] = [Math.min(a.x, b.x), Math.max(a.x, b.x)];
  const [y0, y1] = [Math.min(a.y, b.y), Math.max(a.y, b.y)];
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

export const wholeGlyph = (glyph: TitleGlyph) => rectPolygon({ x: 0, y: 0 }, { x: glyph.width, y: glyph.height });

/** Sredina okvira poligona: oko nje se deo rotira, uvećava i okreće u ogledalu. */
export function polygonCenter(polygon: number[][]): Point {
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => y);
  return { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
}

/** Izrez je upotrebljiv ako ima površinu (bar tri tačke i nije tanji od 2 px). */
export function isArea(polygon: number[][]): boolean {
  if (polygon.length < 3) return false;
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => y);
  return Math.max(...xs) - Math.min(...xs) >= 2 && Math.max(...ys) - Math.min(...ys) >= 2;
}

/** Slobodna linija: tačke bliže od `step` px se preskaču. */
export function addPoint(points: number[][], point: Point, step = 2): number[][] {
  const last = points[points.length - 1];
  if (last && Math.hypot(point.x - last[0], point.y - last[1]) < step) return points;
  return [...points, [point.x, point.y]];
}

/** Nov deo stoji tamo gde je bio u svom slovu, a slovo je na sredini platna i na osnovnoj liniji. */
export function newPart(glyph: TitleGlyph, polygon: number[][], canvas: GlyphCanvas): GlyphPart {
  const center = polygonCenter(polygon);
  const left = canvas.width / 2 - (glyph.ink_left + glyph.ink_right) / 2;
  const top = canvas.baseline - glyph.baseline;
  return { source: glyph.key, polygon, x: left + center.x, y: top + center.y, scaleX: 1, scaleY: 1, rotation: 0 };
}

export function mirrored(part: GlyphPart, axis: "x" | "y"): GlyphPart {
  return axis === "x" ? { ...part, scaleX: -part.scaleX } : { ...part, scaleY: -part.scaleY };
}

function polygonBox(polygon: number[][]) {
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => y);
  return { left: Math.min(...xs), top: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
}

/** Konva položaj izrezanog dela (slika veličine okvira izreza), transformisanog oko svoje sredine. */
export function partPlacement(part: GlyphPart) {
  const box = polygonBox(part.polygon);
  return {
    x: part.x,
    y: part.y,
    offsetX: box.width / 2,
    offsetY: box.height / 2,
    scaleX: part.scaleX,
    scaleY: part.scaleY,
    rotation: part.rotation,
  };
}

/** Izrez iz slike slova: platno veličine okvira poligona, providno van poligona. */
export function cutPart(image: CanvasImageSource, polygon: number[][]): HTMLCanvasElement | null {
  const box = polygonBox(polygon);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(box.width));
  canvas.height = Math.max(1, Math.ceil(box.height));
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.beginPath();
  polygon.forEach(([x, y], index) => (index === 0 ? context.moveTo(x - box.left, y - box.top) : context.lineTo(x - box.left, y - box.top)));
  context.closePath();
  context.clip();
  context.drawImage(image, -box.left, -box.top);
  return canvas;
}

/** Okvir mastila (alfa > 0) u RGBA pikselima platna; null ako je platno prazno. */
export function inkBounds(data: Uint8ClampedArray, width: number, height: number): { left: number; top: number; right: number; bottom: number } | null {
  let left = width;
  let top = height;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (data[(y * width + x) * 4 + 3] > 0) {
        left = Math.min(left, x);
        right = Math.max(right, x);
        top = Math.min(top, y);
        bottom = Math.max(bottom, y);
      }
    }
  }
  return right < 0 ? null : { left, top, right: right + 1, bottom: bottom + 1 };
}
