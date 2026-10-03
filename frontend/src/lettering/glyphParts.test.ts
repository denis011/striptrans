import { describe, expect, it } from "vitest";
import type { TitleGlyph } from "../api";
import { addPoint, inkBounds, isArea, mirrored, newPart, partPlacement, polygonCenter, rectPolygon, toSource, wholeGlyph } from "./glyphParts";

const r: TitleGlyph = { key: "g6", char: "R", source: "original", width: 180, height: 270, baseline: 262, ink_left: 3, ink_right: 177 };
const canvas = { width: 560, height: 460, baseline: 370, capLine: 115 };

describe("slovo od delova", () => {
  it("pravougaonik u bilo kom smeru i sredina izreza", () => {
    expect(rectPolygon({ x: 50, y: 80 }, { x: 10, y: 20 })).toEqual([
      [10, 20],
      [50, 20],
      [50, 80],
      [10, 80],
    ]);
    expect(polygonCenter(wholeGlyph(r))).toEqual({ x: 90, y: 135 });
    expect(isArea(rectPolygon({ x: 5, y: 5 }, { x: 6, y: 40 }))).toBe(false);
    expect(isArea([[0, 0], [10, 0]])).toBe(false);
  });

  it("slobodna linija preskače tačke koje su preblizu", () => {
    const points = addPoint(addPoint([[0, 0]], { x: 1, y: 1 }), { x: 5, y: 0 });
    expect(points).toEqual([
      [0, 0],
      [5, 0],
    ]);
  });

  it("nov deo stoji kao u svom slovu, a slovo je na sredini platna i na osnovnoj liniji", () => {
    const stem = rectPolygon({ x: 3, y: 0 }, { x: 60, y: 270 });
    const part = newPart(r, stem, canvas);
    const placed = partPlacement(part);
    // levi rub izreza (x = 3) je na 280 - 90 + 3 = 193, vrh na 370 - 262 = 108
    expect(placed.x - placed.offsetX).toBeCloseTo(193);
    expect(placed.y - placed.offsetY).toBeCloseTo(108);
    expect([placed.offsetX, placed.offsetY]).toEqual([28.5, 135]);
    expect(mirrored(mirrored(part, "x"), "y")).toMatchObject({ scaleX: -1, scaleY: -1 });
  });

  it("okvir mastila iz RGBA piksela", () => {
    const data = new Uint8ClampedArray(4 * 4 * 3);
    data[(1 * 4 + 2) * 4 + 3] = 255; // (2, 1)
    data[(2 * 4 + 1) * 4 + 3] = 40; // (1, 2)
    expect(inkBounds(data, 4, 3)).toEqual({ left: 1, top: 1, right: 3, bottom: 3 });
    expect(inkBounds(new Uint8ClampedArray(16), 2, 2)).toBeNull();
  });
});

describe("toSource", () => {
  // tačka izvornog slova → platno kao u Konvi (pomeraj, rotacija, razmera oko sredine izreza), pa nazad
  const forward = (part: Parameters<typeof toSource>[0], x: number, y: number) => {
    const placement = partPlacement(part);
    const lx = (x - 10 - placement.offsetX) * placement.scaleX; // izrez počinje na (10, 20)
    const ly = (y - 20 - placement.offsetY) * placement.scaleY;
    const angle = (placement.rotation * Math.PI) / 180;
    return { x: placement.x + lx * Math.cos(angle) - ly * Math.sin(angle), y: placement.y + lx * Math.sin(angle) + ly * Math.cos(angle) };
  };

  it("vraća piksel izvornog slova i za rotiran, uvećan i okrenut deo", () => {
    const polygon = rectPolygon({ x: 10, y: 20 }, { x: 50, y: 80 });
    const part = { source: "g0", polygon, x: 200, y: 150, scaleX: -1.5, scaleY: 0.8, rotation: 30 };
    for (const [x, y] of [[10, 20], [33, 47], [50, 80]]) {
      const back = toSource(part, forward(part, x, y));
      expect(back.x).toBeCloseTo(x);
      expect(back.y).toBeCloseTo(y);
    }
  });
});
