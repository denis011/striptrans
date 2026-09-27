import { describe, expect, it } from "vitest";
import { AUTO_STYLE, type TextBlock, type TitleGlyph, type TitleGlyphs } from "../api";
import { isLettered, letterBlocks } from "./blocks";
import type { FontMetrics } from "./fonts";
import { letteringShapes } from "./shapes";
import { choicesFor, composeTitle } from "./title";

const glyph = (key: string, char: string, extra: Partial<TitleGlyph> = {}): TitleGlyph => ({
  key,
  char,
  source: "original",
  width: 206,
  height: 262,
  baseline: 260,
  ink_left: 3,
  ink_right: 203,
  row: 0,
  space_before: false,
  gap_next: -6,
  ...extra,
});

// PASSACRO!: A se uvlači pod S (razmak -107), ostala slova skoro dodiruju (-6)
const title: TitleGlyphs = {
  version: "v1",
  text: "PASSACRO!",
  light: true,
  ink: 255,
  background: 2,
  left: 169,
  top: 157,
  right: 1613,
  bottom: 421,
  cap_height: 256,
  max_scale: 1.3,
  gap: -6,
  word_gap: 80,
  found: 9,
  expected: 9,
  glyphs: [..."PASSACRO!"].map((char, i) => glyph(`g${i}`, char, { gap_next: i === 8 ? null : i === 1 ? -107 : -6 })),
  extra: [glyph("x0", "K", { source: "fallback" }), glyph("x1", "Š", { source: "accent", height: 330, baseline: 328 })],
};

const keys = (text: string, style = AUTO_STYLE) => composeTitle(text, title, style).letters.map((letter) => letter.key);

describe("naslov od slova originala", () => {
  it("susedi iz originala ostaju susedi, a ponovljeno slovo uzima drugi primerak", () => {
    // M A S iz originala, drugo A je drugi primerak (g4), K je napravljen, R i ! iz originala
    expect(keys("PASAKR!")).toEqual(["g0", "g1", "g2", "g4", "x0", "g6", "g8"]);
    expect(keys("PASSA")).toEqual(["g0", "g1", "g2", "g3", "g4"]);
  });

  it("razmak suseda iz originala je originalni (preklop A i S), ostali srednji", () => {
    const { letters, scale } = composeTitle("PASA", title, { ...AUTO_STYLE, fit: "original" });

    expect(scale).toBe(1);
    const step = (i: number) => letters[i + 1].x - letters[i].x;
    expect(step(0)).toBe(200 - 6); // M → A
    expect(step(1)).toBe(200 - 107); // A → S, uvučeno
    expect(step(2)).toBe(200 - 6); // S → drugo A
  });

  it("kraća reč se uvećava do širine originala, ali ne preko trake", () => {
    const short = composeTitle("PASAKR!", title, AUTO_STYLE);
    const natural = 7 * 200 - 6 - 107 - 6 - 6 - 6 - 6;
    expect(short.scale).toBeCloseTo((1613 - 169) / natural);
    expect(short.x + short.width / 2).toBeCloseTo((169 + 1613) / 2, 0);

    expect(composeTitle("PA", title, AUTO_STYLE).scale).toBe(1.3); // traka ne dozvoljava više
    expect(composeTitle("PA", title, { ...AUTO_STYLE, fit: "original", scale: 0.9 }).scale).toBe(0.9);
  });

  it("slova stoje na osnovnoj liniji i slovo sa kvačicom viri iznad", () => {
    const { letters } = composeTitle("SŠ", title, { ...AUTO_STYLE, fit: "original" });

    expect(letters[0].y + 260).toBeCloseTo(letters[1].y + 328);
    expect(letters[1].y).toBeLessThan(letters[0].y);
  });

  it("razmak slova, reči i ručne izmene pojedinačnog slova", () => {
    const plain = composeTitle("PA", title, { ...AUTO_STYLE, fit: "original" });
    const spaced = composeTitle("PA", title, { ...AUTO_STYLE, fit: "original", letter_spacing: 0.1 });
    expect(spaced.width - plain.width).toBeCloseTo(25.6);

    const words = composeTitle("P A", title, { ...AUTO_STYLE, fit: "original" });
    expect(words.letters[1].x - words.letters[0].x).toBe(200 + 80);

    const style = { ...AUTO_STYLE, fit: "original" as const, letters: { "1": { key: "g4", dx: 0.1, dy: -0.1 } } };
    const nudged = composeTitle("PA", title, style);
    expect(nudged.letters[1].key).toBe("g4");
    expect(nudged.letters[1].x - plain.letters[1].x).toBeCloseTo(25.6);
    expect(nudged.letters[1].y - plain.letters[1].y).toBeCloseTo(-25.6);
  });

  it("pojedinačno slovo se rotira oko svoje sredine (naslov u luku)", () => {
    const style = { ...AUTO_STYLE, letters: { "0": { rotation: -12 } } };
    const { letters } = composeTitle("PASAKR!", title, style);
    expect(letters.map((letter) => letter.rotation)).toEqual([-12, 0, 0, 0, 0, 0, 0]);

    const [lettering] = letterBlocks([{ ...blockFor(), style }], 2457, fonts);
    const { images } = letteringShapes(lettering);
    expect(images[0]).toMatchObject({ rotation: -12, offsetX: images[0].width / 2, offsetY: images[0].height / 2 });
    expect(images[0].x - images[0].offsetX).toBeCloseTo(letters[0].x);
  });

  it("slovo sastavljeno od delova ima prednost nad napravljenim", () => {
    const custom = [glyph("c0", "K", { source: "custom" })];
    expect(composeTitle("KR", { ...title, custom }, AUTO_STYLE).letters[0].key).toBe("c0");
    expect(choicesFor({ ...title, custom }, "K").map((item) => item.key)).toEqual(["c0", "x0"]);
  });

  it("izbor primerka za drugo slovo se ne primenjuje, a slovo bez slike se prijavljuje", () => {
    expect(keys("PA", { ...AUTO_STYLE, letters: { "1": { key: "g0" } } })).toEqual(["g0", "g1"]);
    expect(composeTitle("PÜ", title, AUTO_STYLE).missing).toEqual(["Ü"]);
    expect(choicesFor(title, "A").map((item) => item.key)).toEqual(["g1", "g4"]);
  });
});

const font: FontMetrics = { family: "f", capRatio: 0.7, measure: (text) => text.length * 0.6 };
const fonts = { dialogue: font, sound: font, byKey: () => undefined };
const blockFor = (changes: Partial<TextBlock> = {}): TextBlock => ({
  id: 7,
  page_id: 1,
  position: 1,
  kind: "title",
  x: 130,
  y: 117,
  width: 1506,
  height: 300,
  bubble_polygon: null,
  ocr_text: null,
  text: "PASSACRO!",
  confidence: null,
  ocr_model: null,
  source: "manual",
  needs_review: false,
  translation: "PASAKR!",
  translation_model: null,
  translation_status: "edited",
  translation_too_long: false,
  title,
  ...changes,
  });

describe("naslov na stranici", () => {
  const block = blockFor;

  it("slaže se slikama slova, sa verzijom u adresi", () => {
    const [lettering] = letterBlocks([block({})], 2457, fonts);

    expect(lettering.images?.map((image) => image.url)[4]).toBe("/api/blocks/7/glyphs/x0.png?v=v1");
    expect(lettering.layout.fits).toBe(true);
    expect(lettering.light).toBe(true);
  });

  it("šuplja slova su neprovidna: prvo ispune svih slova, pa konture preko njih", () => {
    const hollow = { ...title, hollow: true, glyphs: title.glyphs.map((item) => ({ ...item, fill: true })) };
    const urls = (style = AUTO_STYLE) => letterBlocks([block({ title: hollow, style })], 2457, fonts)[0].images?.map((image) => image.url.split("/").pop());

    const opaque = urls();
    expect(opaque?.slice(0, 2)).toEqual(["g0f.png?v=v1", "g1f.png?v=v1"]);
    expect(opaque).toHaveLength(6 + 7); // K je napravljeno slovo bez ispune
    expect(urls({ ...AUTO_STYLE, opaque: false })).toHaveLength(7);
    expect(letterBlocks([block({})], 2457, fonts)[0].images).toHaveLength(7); // puna slova: bez ispune
  });

  it("neprevedeni naslov ostaje original, a naslov bez isečenih slova se slaže fontom", () => {
    expect(isLettered(block({ translation: "PASSACRO!" }))).toBe(false);
    const [lettering] = letterBlocks([block({ title: null })], 2457, fonts);
    expect(lettering.images).toBeUndefined();
    expect(lettering.layout.lines).toEqual(["PASAKR!"]);
  });
});
