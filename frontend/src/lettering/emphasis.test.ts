import { describe, expect, it } from "vitest";
import { EMPHASIS_BOLD, emphasisMeasure, splitRuns, stripMarks } from "./emphasis";

const measure = (text: string) => text.length * 0.6;

describe("naglasak", () => {
  it("deli red na običan i naglašen tekst", () => {
    expect(splitRuns("REKAO JE TO KRALJICI *LARI*, KAD")).toEqual([
      { text: "REKAO JE TO KRALJICI ", emphasis: false },
      { text: "LARI", emphasis: true },
      { text: ", KAD", emphasis: false },
    ]);
    expect(splitRuns("*PROKLETI MLAKONJO!*")).toEqual([{ text: "PROKLETI MLAKONJO!", emphasis: true }]);
    expect(splitRuns("„*REKAO* JE")).toEqual([
      { text: "„", emphasis: false },
      { text: "REKAO", emphasis: true },
      { text: " JE", emphasis: false },
    ]);
    expect(splitRuns("BEZ NAGLASKA")).toEqual([{ text: "BEZ NAGLASKA", emphasis: false }]);
  });

  it("rastavljena naglašena reč ostaje naglašena u oba reda", () => {
    expect(splitRuns("OSEĆAM SE *BESKORI-")).toEqual([
      { text: "OSEĆAM SE ", emphasis: false },
      { text: "BESKORI-", emphasis: true },
    ]);
    expect(splitRuns("SNO*.")).toEqual([
      { text: "SNO", emphasis: true },
      { text: ".", emphasis: false },
    ]);
  });

  it("zvezdice nemaju širinu, a naglašen tekst je malo širi", () => {
    const measured = emphasisMeasure(measure);
    expect(measured("REKAO JE")).toBe(measure("REKAO JE"));
    expect(measured("*LARI*")).toBeGreaterThan(measure("LARI") + 4 * EMPHASIS_BOLD - 1e-9);
    expect(emphasisMeasure(measure, true)("LARI")).toBe(measured("*LARI*"));
    expect(stripMarks("*LARI*, KAD")).toBe("LARI, KAD");
  });
});

describe("dugme B (Ctrl+B)", () => {
  it("naglašava izabrani deo, a razmaci i interpunkcija ostaju van zvezdica", async () => {
    const { toggleEmphasis } = await import("./emphasis");
    const text = "NEKU VRSTU ORLA!";
    expect(toggleEmphasis(text, 11, 16).text).toBe("NEKU VRSTU *ORLA*!");
    expect(toggleEmphasis(text, 10, 15).text).toBe("NEKU VRSTU *ORLA*!"); // razmak ispred izbora
    expect(toggleEmphasis("PROKLETA KUKAVICO!", 0, 18).text).toBe("*PROKLETA KUKAVICO*!");
  });

  it("bez izbora naglašava reč na kojoj je kursor, a drugi put je vraća u običnu", async () => {
    const { toggleEmphasis } = await import("./emphasis");
    const once = toggleEmphasis("NEKU VRSTU ORLA!", 13, 13);
    expect(once.text).toBe("NEKU VRSTU *ORLA*!");
    expect(toggleEmphasis(once.text, 13, 13).text).toBe("NEKU VRSTU ORLA!");
    expect(toggleEmphasis(once.text, once.start, once.end).text).toBe("NEKU VRSTU ORLA!");
  });
});
