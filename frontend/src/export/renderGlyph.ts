// Sastavljeno slovo (Faza 6b) kao PNG sa providnošću: isti delovi kao u prozoru „Novo slovo".

import Konva from "konva";
import type { GlyphPart } from "../api";
import { type GlyphCanvas, cutPart, inkBounds, partPlacement } from "../lettering/glyphParts";

const PAD = 3; // prazan rub oko slova, kao kod isečenih slova

function draw(parts: GlyphPart[], images: Map<string, HTMLImageElement>, canvas: GlyphCanvas): HTMLCanvasElement {
  const stage = new Konva.Stage({ container: document.createElement("div"), width: canvas.width, height: canvas.height });
  try {
    const layer = new Konva.Layer();
    for (const part of parts) {
      const source = images.get(part.source);
      const image = source && cutPart(source, part.polygon);
      if (image) layer.add(new Konva.Image({ image, ...partPlacement(part) }));
    }
    stage.add(layer);
    return stage.toCanvas({ pixelRatio: 1 });
  } finally {
    stage.destroy();
  }
}

function bounds(full: HTMLCanvasElement) {
  const context = full.getContext("2d");
  return context ? inkBounds(context.getImageData(0, 0, full.width, full.height).data, full.width, full.height) : null;
}

function cropped(full: HTMLCanvasElement, left: number, top: number, width: number, height: number): Promise<Blob | null> {
  const crop = document.createElement("canvas");
  crop.width = width;
  crop.height = height;
  crop.getContext("2d")?.drawImage(full, left, top, width, height, 0, 0, width, height);
  return new Promise((resolve) => crop.toBlob(resolve, "image/png"));
}

/**
 * Slovo i, ako izvorna slova imaju ispunu (šuplja slova), ispuna od istih delova; obe slike su
 * isečene na isti okvir.
 */
export async function renderGlyph(
  parts: GlyphPart[],
  images: Map<string, HTMLImageElement>,
  canvas: GlyphCanvas,
  fills?: Map<string, HTMLImageElement>,
): Promise<{ blob: Blob; fill?: Blob; baseline: number } | null> {
  const ink = draw(parts, images, canvas);
  const inkBox = bounds(ink);
  if (!inkBox) return null;
  // delovi čije izvorno slovo nema ispunu se u ispuni preskaču
  const filled = fills?.size ? draw(parts, fills, canvas) : null;
  const fillBox = filled ? bounds(filled) : null;
  const box = fillBox
    ? { left: Math.min(inkBox.left, fillBox.left), top: Math.min(inkBox.top, fillBox.top), right: Math.max(inkBox.right, fillBox.right), bottom: Math.max(inkBox.bottom, fillBox.bottom) }
    : inkBox;
  const left = Math.max(0, box.left - PAD);
  const top = Math.max(0, box.top - PAD);
  const width = Math.min(ink.width, box.right + PAD) - left;
  const height = Math.min(ink.height, box.bottom + PAD) - top;
  const blob = await cropped(ink, left, top, width, height);
  if (!blob) return null;
  const fill = filled && fillBox ? ((await cropped(filled, left, top, width, height)) ?? undefined) : undefined;
  return { blob, fill, baseline: canvas.baseline - top };
}
