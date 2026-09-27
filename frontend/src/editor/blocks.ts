import type { BlockKind, Rect } from "../api";
import type { Point, Size } from "../viewer/zoom";

export const BLOCK_KINDS: { kind: BlockKind; label: string; color: string }[] = [
  { kind: "speech", label: "Govor", color: "#2563eb" },
  { kind: "thought", label: "Misao", color: "#7c3aed" },
  { kind: "caption", label: "Naracija", color: "#059669" },
  { kind: "sfx", label: "Onomatopeja", color: "#dc2626" },
  { kind: "other", label: "Ostalo", color: "#6b7280" },
  { kind: "title", label: "Naslov", color: "#d97706" },
];

export const MIN_BLOCK_SIZE = 8;

export function kindColor(kind: BlockKind): string {
  return BLOCK_KINDS.find((item) => item.kind === kind)?.color ?? "#6b7280";
}

/** Pravougaonik iz početne i krajnje tačke prevlačenja, u bilo kom smeru. */
export function rectFromPoints(a: Point, b: Point): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  };
}

/** Pravougaonik sečen na granice stranice. */
export function clampRect(rect: Rect, page: Size): Rect {
  const x = Math.min(Math.max(rect.x, 0), page.width);
  const y = Math.min(Math.max(rect.y, 0), page.height);
  return {
    x,
    y,
    width: Math.max(0, Math.min(rect.x + rect.width, page.width) - x),
    height: Math.max(0, Math.min(rect.y + rect.height, page.height) - y),
  };
}

/** Selekcija posle klika: sa Shift/Ctrl dodaje ili uklanja blok, inače bira samo njega. */
export function toggleSelection(selected: number[], id: number, additive: boolean): number[] {
  if (!additive) return [id];
  return selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
}

/** Zameni blok sa susedom (-1 gore, +1 dole). */
export function moveBlock(ids: number[], id: number, delta: number): number[] {
  const from = ids.indexOf(id);
  const to = from + delta;
  if (from === -1 || to < 0 || to >= ids.length) return ids;
  const result = [...ids];
  [result[from], result[to]] = [result[to], result[from]];
  return result;
}
