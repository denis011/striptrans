import { describe, expect, it } from "vitest";
import { clampRect, moveBlock, rectFromPoints, toggleSelection } from "./blocks";

describe("blocks", () => {
  it("pravi pravougaonik prevlačenjem u bilo kom smeru", () => {
    expect(rectFromPoints({ x: 50, y: 80 }, { x: 10, y: 20 })).toEqual({ x: 10, y: 20, width: 40, height: 60 });
  });

  it("seče pravougaonik na granice stranice", () => {
    const page = { width: 100, height: 200 };
    expect(clampRect({ x: -10, y: 150, width: 50, height: 100 }, page)).toEqual({ x: 0, y: 150, width: 40, height: 50 });
  });

  it("bira jedan blok ili dodaje i uklanja uz Shift", () => {
    expect(toggleSelection([1, 2], 3, false)).toEqual([3]);
    expect(toggleSelection([1, 2], 3, true)).toEqual([1, 2, 3]);
    expect(toggleSelection([1, 2], 2, true)).toEqual([1]);
  });

  it("pomera blok gore i dole, ali ne van liste", () => {
    expect(moveBlock([1, 2, 3], 2, -1)).toEqual([2, 1, 3]);
    expect(moveBlock([1, 2, 3], 2, 1)).toEqual([1, 3, 2]);
    const ids = [1, 2, 3];
    expect(moveBlock(ids, 1, -1)).toBe(ids);
  });
});
