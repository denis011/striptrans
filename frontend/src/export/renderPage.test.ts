import { describe, expect, it } from "vitest";
import { pageFilename, softEdges } from "./renderPage";

describe("ime fajla stranice", () => {
  it("serijal, broj i strana sa nulama", () => {
    expect(pageFilename("Ramon", "12", 9, "jpeg")).toBe("ramon-12-009.jpg");
    expect(pageFilename("Ramon (srpsko izdanje)", null, 120, "png")).toBe("ramon-srpsko-izdanje-120.png");
    expect(pageFilename("Đavolji Čovek", "1", 1, "jpeg")).toBe("davolji-covek-1-001.jpg");
  });
});

describe("meke ivice teksta", () => {
  const image = () => {
    const data = new Uint8ClampedArray(3 * 3 * 4);
    data.set([0, 0, 0, 255], 4 * 4); // jedan crn piksel u sredini, ostalo providno
    return { data, width: 3, height: 3 } as unknown as ImageData;
  };

  it("bez jačine slika ostaje ista, a sa jačinom se ivica razliva na susede", () => {
    const sharp = image();
    softEdges(0)(sharp);
    expect(Array.from(sharp.data.filter((_, i) => i % 4 === 3))).toEqual([0, 0, 0, 0, 255, 0, 0, 0, 0]);

    const soft = image();
    softEdges(0.3)(soft);
    const alpha = Array.from(soft.data.filter((_, i) => i % 4 === 3));
    expect(alpha[4]).toBeLessThan(255);
    expect(alpha[4]).toBeGreaterThan(150);
    expect(alpha[1]).toBeGreaterThan(0); // sused dobija deo mastila
  });
});
