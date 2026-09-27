export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface View {
  scale: number;
  x: number;
  y: number;
}

/** page: cela stranica je vidljiva; width: stranica popunjava širinu; actual: 100 %. */
export type FitMode = "page" | "width" | "actual";

export const MIN_SCALE = 0.05;
export const MAX_SCALE = 8;
export const ZOOM_STEP = 1.15;

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

/** Pogled koji uklapa sliku u kontejner; horizontalno centrira, vertikalno centrira ako staje. */
export function fitView(container: Size, image: Size, mode: FitMode): View {
  const byWidth = container.width / image.width;
  const byHeight = container.height / image.height;
  const scale = clampScale(
    mode === "actual" ? 1 : mode === "width" ? byWidth : Math.min(byWidth, byHeight),
  );
  return {
    scale,
    x: (container.width - image.width * scale) / 2,
    y: Math.max(0, (container.height - image.height * scale) / 2),
  };
}

/** Zum oko tačke (npr. pokazivača miša) tako da ta tačka slike ostane na istom mestu. */
export function zoomAt(view: View, pointer: Point, factor: number): View {
  const scale = clampScale(view.scale * factor);
  const imageX = (pointer.x - view.x) / view.scale;
  const imageY = (pointer.y - view.y) / view.scale;
  return { scale, x: pointer.x - imageX * scale, y: pointer.y - imageY * scale };
}

export interface Box extends Point, Size {}

/**
 * Okvir sa stranice u pikselima ekrana, za polja koja stoje iznad canvas-a (izmena teksta u bloku).
 * Sitan okvir se razvlači do najmanje mere oko svoje sredine, da polje ostane upotrebljivo.
 */
export function screenRect(view: View, box: Box, min: Size = { width: 0, height: 0 }): Box {
  const width = Math.max(box.width * view.scale, min.width);
  const height = Math.max(box.height * view.scale, min.height);
  return {
    x: view.x + (box.x + box.width / 2) * view.scale - width / 2,
    y: view.y + (box.y + box.height / 2) * view.scale - height / 2,
    width,
    height,
  };
}
