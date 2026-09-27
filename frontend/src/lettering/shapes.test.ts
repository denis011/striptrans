import { describe, expect, it } from "vitest";
import { AUTO_STYLE } from "../api";
import { type Lettering, lineRuns } from "./blocks";
import { EMPHASIS_BOLD, emphasisMeasure } from "./emphasis";
import { OVERFLOW_COLOR, letteringShapes } from "./shapes";

const item: Lettering = {
  id: 1,
  family: "st-comic",
  outline: false,
  light: false,
  words: null,
  style: { ...AUTO_STYLE, dx: 10, dy: -5, rotation: 15 },
  center: { x: 200, y: 100 },
  layout: {
    lines: ["TO JE", "ON!"],
    placements: [
      { x: 150, y: 80, width: 100 },
      { x: 160, y: 100, width: 80 },
    ],
    size: 30,
    lineHeight: 1.2,
    x: 150,
    y: 80,
    width: 100,
    height: 72,
    fits: true,
  },
};

describe("oblici složenog teksta", () => {
  it("grupa se pomera i rotira oko sredine teksta", () => {
    const { group, texts } = letteringShapes(item);

    expect(group).toEqual({ x: 210, y: 95, offsetX: 200, offsetY: 100, rotation: 15 });
    // rezerva od jedne veličine slova (30), pola levo, pola desno: sredina reda ostaje ista
    expect(texts.map((text) => [text.text, text.x, text.width])).toEqual([
      ["TO JE", 135, 130],
      ["ON!", 145, 110],
    ]);
  });

  it("tekst koji ne staje je crven samo u editoru, ne i u izvozu", () => {
    const overflowing = { ...item, layout: { ...item.layout, fits: false } };

    expect(letteringShapes(overflowing).texts[0].fill).toBe(OVERFLOW_COLOR);
    expect(letteringShapes(overflowing, false).texts[0].fill).toBe("#000");
  });

  it("onomatopeja dobija beli obrub srazmeran slovima", () => {
    const { texts } = letteringShapes({ ...item, outline: true });

    expect(texts[0].stroke).toBe("#fff");
    expect(texts[0].strokeWidth).toBeCloseTo(3.6);
  });

  it("na tamnoj podlozi slova su bela, a obrub onomatopeje crn", () => {
    const { texts } = letteringShapes({ ...item, light: true, outline: true });

    expect(texts[0].fill).toBe("#fff");
    expect(texts[0].stroke).toBe("#000");
  });

  it("boja iz stila bloka menja automatsku (naslovna, kolor strane)", () => {
    const { texts } = letteringShapes({ ...item, light: true, style: { ...item.style, color: "#ffd400" } });

    expect(texts[0].fill).toBe("#ffd400");
    expect(texts[0].stroke).toBeUndefined(); // obrub nije zadat
  });

  it("zadat obrub važi i za govor, a debljina 0 ga uklanja i sa onomatopeje", () => {
    const edged = letteringShapes({ ...item, style: { ...item.style, color: "#ffd400", outline_color: "#d7261e" } });
    const none = letteringShapes({ ...item, outline: true, style: { ...item.style, outline_width: 0 } });

    expect(edged.texts[0].stroke).toBe("#d7261e");
    expect(edged.texts[0].strokeWidth).toBeCloseTo(3.6); // automatska debljina, kao kod onomatopeje
    expect(none.texts[0].stroke).toBeUndefined();
  });

  it("kos naslov se vraća pod ugao i u kurziv originala, a ručna rotacija se dodaje", () => {
    const { group } = letteringShapes({ ...item, tilt: 8.5, skew: 0.36 });

    expect(group.rotation).toBeCloseTo(15 + 8.5);
    expect(group.skewX).toBeCloseTo(-0.36);
    expect(letteringShapes(item).group.skewX).toBeUndefined(); // uspravan tekst ostaje bez smicanja
  });

  it("obostrano poravnat red se crta reč po reč, poslednji red centrirano", () => {
    const words = [[{ text: "TO", x: 150 }, { text: "JE", x: 210 }], null];
    const { texts } = letteringShapes({ ...item, words, style: { ...item.style, align: "justify" } });

    expect(texts.map((text) => [text.text, text.x, text.align])).toEqual([
      ["TO", 150, "left"],
      ["JE", 210, "left"],
      ["ON!", 145, "center"],
    ]);
    expect(texts[0].width).toBeUndefined(); // reč se ne odseca
  });
});

describe("naglasak", () => {
  const measure = (text: string) => text.length * 0.6;

  it("naglašena reč u redu se crta posebno: podebljana i nagnuta, ostatak reda obično", () => {
    const layout = { ...item.layout, lines: ["TO JE *ON*!"], placements: [{ x: 100, y: 80, width: 300 }] };
    const runs = lineRuns(layout, measure, "center", null, false, false);
    const texts = letteringShapes({ ...item, layout, runs }).texts;

    expect(texts.map((text) => text.text)).toEqual(["TO JE ", "ON", "!"]);
    const [plain, bold, after] = texts;
    expect(plain.skewX).toBeUndefined();
    expect(bold.skewX).toBeLessThan(0);
    expect(bold.stroke).toBe(bold.fill); // podebljanje: potez iste boje kao slova
    expect(bold.strokeWidth).toBeCloseTo(EMPHASIS_BOLD * 30);
    expect(after.x).toBeGreaterThan(bold.x);
    // red je centriran u svom mestu
    const width = emphasisMeasure(measure)("TO JE *ON*!") * 30;
    expect(runs?.[0]?.[0].x).toBeCloseTo(100 + (300 - width) / 2);
  });

  it("bez naglaska redovi se crtaju celi, kao pre", () => {
    expect(lineRuns(item.layout, measure, "center", null, false, false)).toBeNull();
  });

  it("naglašen ceo blok i ukošena naracija", () => {
    const all = lineRuns(item.layout, measure, "center", null, true, false);
    expect(all?.every((line) => line?.every((run) => run.emphasis))).toBe(true);
    const italic = lineRuns(item.layout, measure, "center", null, false, true);
    const texts = letteringShapes({ ...item, runs: italic, italic: true }).texts;
    expect(texts.every((text) => (text.skewX ?? 0) < 0 && !text.letterSpacing)).toBe(true);
  });

  it("naglašena onomatopeja sa obrubom: prvo obrub, pa podebljana slova", () => {
    const layout = { ...item.layout, lines: ["*BUM*"], placements: [{ x: 100, y: 80, width: 300 }] };
    const runs = lineRuns(layout, measure, "center", null, false, false);
    const texts = letteringShapes({ ...item, outline: true, layout, runs }).texts;
    expect(texts).toHaveLength(2);
    expect(texts[0].stroke).toBe("#fff");
    expect(texts[1].stroke).toBe(texts[1].fill);
  });
});
