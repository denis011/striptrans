import { describe, expect, it } from "vitest";
import type { Page } from "./api";
import { importRanks, isReordered } from "./pageOrder";

function page(id: number, position: number, importOrder: number): Page {
  const size = { width: 1, height: 1, skip: false, ocr_reviewed: false, translation_reviewed: false };
  return { id, kind: "original", position, import_order: importOrder, source_name: "", ...size };
}

describe("pageOrder", () => {
  it("posle brisanja stranice redosled nije izmenjen", () => {
    expect(isReordered([page(1, 1, 1), page(3, 2, 3)])).toBe(false);
  });

  it("zamena stranica menja redosled i daje izvorne brojeve", () => {
    const pages = [page(2, 1, 2), page(1, 2, 1), page(3, 3, 3)];

    expect(isReordered(pages)).toBe(true);
    expect(importRanks(pages)).toEqual(new Map([[1, 1], [2, 2], [3, 3]]));
  });
});
