import { describe, expect, it } from "vitest";
import { blocks } from "../test/fixtures";
import { blockStyle, isLettered, justifyLines } from "./blocks";
import type { Layout } from "./layout";

const base = { ...blocks[0], translation: "", translation_status: "draft" as const };

describe("koji se blokovi slažu na slici", () => {
  it("oblačić sa prevodom da, bez prevoda ne", () => {
    expect(isLettered({ ...base, translation: "ZDRAVO" })).toBe(true);
    expect(isLettered(base)).toBe(false);
  });

  it("natpis i onomatopeja samo kad je prevod drugačiji od originala", () => {
    expect(isLettered({ ...base, kind: "other", text: "SHERIFF", translation: "ŠERIF" })).toBe(true);
    expect(isLettered({ ...base, kind: "sfx", text: "AH!", translation: "AH!" })).toBe(false);
    expect(isLettered({ ...base, kind: "sfx", text: "SWACK", translation: "" })).toBe(false);
  });

  it("onomatopeja nasleđuje nagib originala dok se ručno ne promeni", () => {
    const sound = { ...base, kind: "sfx" as const, angle: -12 };

    expect(blockStyle(sound).rotation).toBe(-12);
    expect(blockStyle({ ...sound, style: { ...blockStyle(sound), rotation: 5 } }).rotation).toBe(5);
    expect(blockStyle({ ...base, angle: -12 }).rotation).toBe(0); // oblačići se ne rotiraju sami
  });

  it("obostrano: redovi se razvlače do najšireg reda, poslednji ostaje", () => {
    const measure = (text: string) => text.length * 0.6; // monospace, veličina 10 → 6 px po znaku
    const layout: Layout = {
      lines: ["NEKI DUGAČAK RED", "KRAĆI RED", "KRAJ"],
      placements: [
        { x: 0, y: 0, width: 200, },
        { x: 0, y: 12, width: 200 },
        { x: 0, y: 24, width: 200 },
      ],
      size: 10,
      lineHeight: 1.2,
      x: 0,
      y: 0,
      width: 200,
      height: 36,
      fits: true,
    };

    const [first, second, last] = justifyLines(layout, measure);

    // najširi red: 16 znakova = 96 px, centriran u 200 → od 52 do 148
    const end = (words: { text: string; x: number }[]) => words[words.length - 1].x + words[words.length - 1].text.length * 6;
    expect(first?.[0].x).toBeCloseTo(52);
    expect(end(first ?? [])).toBeCloseTo(148);
    expect(second?.[0].x).toBeCloseTo(52); // kraći red se razvlači na istu širinu
    expect(end(second ?? [])).toBeCloseTo(148);
    expect(last).toBeNull();
  });
});
