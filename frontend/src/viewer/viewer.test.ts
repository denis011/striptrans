import { describe, expect, it } from "vitest";
import { cropRect, fitInto, moveItem, nudgeForKey, positionForKey } from "./navigation";
import { MAX_SCALE, fitView, screenRect, zoomAt } from "./zoom";

const page = { width: 1801, height: 2457 };

describe("fitView", () => {
  it("uklapa celu stranicu i centrira je", () => {
    const view = fitView({ width: 1000, height: 800 }, page, "page");
    expect(view.scale).toBeCloseTo(800 / 2457);
    expect(view.x).toBeCloseTo((1000 - 1801 * view.scale) / 2);
    expect(view.y).toBeCloseTo(0);
  });

  it("po širini popunjava širinu i kreće od vrha", () => {
    const view = fitView({ width: 1000, height: 800 }, page, "width");
    expect(view.scale).toBeCloseTo(1000 / 1801);
    expect(view.x).toBeCloseTo(0);
    expect(view.y).toBe(0);
  });

  it("100 % prikazuje sliku u izvornoj veličini", () => {
    expect(fitView({ width: 1000, height: 800 }, page, "actual").scale).toBe(1);
  });
});

describe("zoomAt", () => {
  it("tačka ispod pokazivača ostaje na mestu", () => {
    const view = { scale: 0.5, x: 100, y: 50 };
    const pointer = { x: 400, y: 300 };
    const zoomed = zoomAt(view, pointer, 2);
    const before = { x: (pointer.x - view.x) / view.scale, y: (pointer.y - view.y) / view.scale };
    const after = {
      x: (pointer.x - zoomed.x) / zoomed.scale,
      y: (pointer.y - zoomed.y) / zoomed.scale,
    };
    expect(zoomed.scale).toBe(1);
    expect(after.x).toBeCloseTo(before.x);
    expect(after.y).toBeCloseTo(before.y);
  });

  it("ne prelazi najveći zum", () => {
    expect(zoomAt({ scale: 7, x: 0, y: 0 }, { x: 0, y: 0 }, 10).scale).toBe(MAX_SCALE);
  });
});

describe("screenRect", () => {
  const view = { scale: 0.5, x: 100, y: 50 };

  it("prenosi okvir sa stranice na ekran", () => {
    expect(screenRect(view, { x: 200, y: 400, width: 300, height: 80 })).toEqual({
      x: 100 + 200 * 0.5,
      y: 50 + 400 * 0.5,
      width: 150,
      height: 40,
    });
  });

  it("sitan okvir razvlači do najmanje mere, oko iste sredine", () => {
    const box = { x: 200, y: 400, width: 20, height: 10 };
    const rect = screenRect(view, box, { width: 160, height: 48 });
    expect(rect.width).toBe(160);
    expect(rect.height).toBe(48);
    expect(rect.x + rect.width / 2).toBeCloseTo(view.x + (box.x + box.width / 2) * view.scale);
    expect(rect.y + rect.height / 2).toBeCloseTo(view.y + (box.y + box.height / 2) * view.scale);
  });
});

describe("positionForKey", () => {
  it.each([
    ["ArrowRight", 5, 6],
    ["PageDown", 5, 6],
    ["ArrowLeft", 5, 4],
    ["PageUp", 5, 4],
    ["Home", 5, 1],
    ["End", 5, 100],
  ])("%s sa strane %i vodi na %i", (key, current, expected) => {
    expect(positionForKey(key, current, 100)).toBe(expected);
  });

  it("ne izlazi van opsega i ignoriše ostale tastere", () => {
    expect(positionForKey("ArrowLeft", 1, 100)).toBeNull();
    expect(positionForKey("ArrowRight", 100, 100)).toBeNull();
    expect(positionForKey("a", 5, 100)).toBeNull();
  });
});

describe("moveItem", () => {
  it("premešta stavku na mesto ciljne", () => {
    expect(moveItem([1, 2, 3, 4], 1, 3)).toEqual([2, 3, 1, 4]);
    expect(moveItem([1, 2, 3, 4], 4, 2)).toEqual([1, 4, 2, 3]);
  });

  it("ne menja listu kad je cilj ista stavka", () => {
    const ids = [1, 2, 3];
    expect(moveItem(ids, 2, 2)).toBe(ids);
  });
});

describe("nudgeForKey", () => {
  it("strelice pomeraju za 1 px, sa Shift-om za 10 px", () => {
    expect(nudgeForKey("ArrowLeft", false)).toEqual([-1, 0]);
    expect(nudgeForKey("ArrowDown", true)).toEqual([0, 10]);
    expect(nudgeForKey("PageDown", false)).toBeNull();
  });
});

describe("cropRect", () => {
  it("dodaje marginu od 10 px i ostaje unutar stranice", () => {
    expect(cropRect({ x: 5, y: 100, width: 50, height: 20 }, { width: 60, height: 500 })).toEqual({ x: 0, y: 90, width: 60, height: 40 });
  });
});

describe("fitInto", () => {
  it("uklapa sliku u okvir bez izobličenja, na sredini", () => {
    // Gemini: 1024 × 163 umesto isečka 1577 × 271 → iste širine, niža, centrirana po visini
    const fitted = fitInto({ x: 127, y: 107, width: 1577, height: 271 }, { width: 1024, height: 163 });
    expect(fitted.width).toBeCloseTo(1577);
    expect(fitted.height).toBeCloseTo(251.0, 0);
    expect(fitted.y).toBeCloseTo(107 + (271 - fitted.height) / 2);
  });
});
