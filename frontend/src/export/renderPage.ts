// Stranica u punoj rezoluciji originala za izvoz: isti oblici teksta kao u editoru (WYSIWYG).

import Konva from "konva";
import type { Patch } from "../api";
import type { Lettering } from "../lettering/blocks";
import { letteringShapes } from "../lettering/shapes";

export type ImageFormat = "jpeg" | "png";

export interface RenderOptions {
  imageUrl: string;
  width: number;
  height: number;
  lettering: Lettering[];
  patches?: Patch[]; // zakrpe slikom (Faza 6c)
  format: ImageFormat;
  quality?: number; // JPEG, 0–1
  softness?: number; // omekšavanje ivica teksta (0–1); 0 = oštro kao font
}

export const DEFAULT_QUALITY = 0.92;
// Ivica slova na skenu srpskog izdanja je mekša od oštrog crtanja fonta; 0,3 je vizuelno najbliže skenu
export const EDGE_SOFTNESS = 0.3;

export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`slika nije učitana: ${url}`));
    image.src = url;
  });
}

/**
 * Blago omekšavanje ivica: mešavina slike i njenog zamućenja 3×3 (Konva Blur je grublji od
 * najmanjeg koraka koji treba). `strength` 0–1 je udeo zamućenja.
 */
export function softEdges(strength: number) {
  return (image: ImageData) => {
    const { data, width, height } = image;
    const source = data.slice();
    const weights = [1, 2, 1, 2, 4, 2, 1, 2, 1];
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const index = (y * width + x) * 4;
        for (let channel = 0; channel < 4; channel += 1) {
          let sum = 0;
          let total = 0;
          for (let k = 0; k < 9; k += 1) {
            const nx = x + (k % 3) - 1;
            const ny = y + Math.floor(k / 3) - 1;
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
            sum += source[(ny * width + nx) * 4 + channel] * weights[k];
            total += weights[k];
          }
          data[index + channel] = source[index + channel] * (1 - strength) + (sum / total) * strength;
        }
      }
    }
  };
}

/** Nacrtaj stranicu (slika + složen prevod) u veličini originala i vrati JPEG ili PNG. */
export async function renderPage({ imageUrl, width, height, lettering, patches = [], format, quality = DEFAULT_QUALITY, softness = EDGE_SOFTNESS }: RenderOptions): Promise<Blob> {
  const image = await loadImage(imageUrl);
  const letterUrls = [...new Set(lettering.flatMap((item) => item.images?.map((letter) => letter.url) ?? []))];
  const letters = new Map(await Promise.all(letterUrls.map(async (url) => [url, await loadImage(url)] as const)));
  const patchImages = new Map(await Promise.all(patches.map(async (patch) => [patch.url, await loadImage(patch.url)] as const)));
  const drawPatches = (layer: Konva.Layer, above: boolean) => {
    for (const patch of patches.filter((item) => item.above_text === above)) {
      const { x, y, width: w, height: h, rotation, opacity } = patch;
      layer.add(new Konva.Image({ image: patchImages.get(patch.url), x, y, width: w, height: h, rotation, opacity }));
    }
  };
  const stage = new Konva.Stage({ container: document.createElement("div"), width, height });
  try {
    const layer = new Konva.Layer();
    layer.add(new Konva.Rect({ width, height, fill: "#fff" }));
    layer.add(new Konva.Image({ image, width, height }));
    drawPatches(layer, false);
    for (const item of lettering) {
      // u izvozu tekst koji ne staje nije crven: to je samo upozorenje u editoru
      const { group, texts, images } = letteringShapes(item, false);
      const node = new Konva.Group(group);
      for (const text of texts) node.add(new Konva.Text(text));
      for (const { url, ...rect } of images) node.add(new Konva.Image({ image: letters.get(url), ...rect }));
      layer.add(node);
      if (texts.length && softness > 0) {
        // ivica slova kao na skenu: prelaz mastilo → papir širi od oštrog crtanja fonta
        node.cache({ pixelRatio: 1 });
        node.filters([softEdges(softness)]);
      }
    }
    drawPatches(layer, true);
    stage.add(layer);
    const blob = await stage.toBlob({ mimeType: `image/${format}`, quality, pixelRatio: 1 });
    if (!(blob instanceof Blob)) throw new Error("stranica nije nacrtana");
    return blob;
  } finally {
    stage.destroy();
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Ime fajla stranice: ramon-12-009.jpg */
export function pageFilename(series: string, issue: string | null, position: number, format: ImageFormat): string {
  const slug = (text: string) =>
    text
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/đ/gi, "d")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  const parts = [slug(series), issue ? slug(issue) : null, String(position).padStart(3, "0")].filter(Boolean);
  return `${parts.join("-")}.${format === "jpeg" ? "jpg" : "png"}`;
}
