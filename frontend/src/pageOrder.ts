import type { Page } from "./api";

/** Izvorni redni broj svake stranice (po redosledu uvoza) među prosleđenim stranicama iste vrste. */
export function importRanks(pages: Page[]): Map<number, number> {
  const sorted = [...pages].sort((a, b) => a.import_order - b.import_order);
  return new Map(sorted.map((page, index) => [page.id, index + 1]));
}

/** Da li se trenutni redosled razlikuje od redosleda uvoza (brisanje stranica se ne računa). */
export function isReordered(pages: Page[]): boolean {
  const ranks = importRanks(pages);
  return pages.some((page) => ranks.get(page.id) !== page.position);
}
