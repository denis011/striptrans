import { describe, expect, it } from "vitest";
import { hyphenationPoints, splitToFit, syllables, units } from "./hyphenate";

describe("rastavljanje reči", () => {
  it("čuva LJ, NJ i DŽ kao jedan glas", () => {
    expect(units("ZNATIŽELJE")).toEqual(["Z", "N", "A", "T", "I", "Ž", "E", "LJ", "E"]);
    expect(units("DŽEJN")).toEqual(["DŽ", "E", "J", "N"]);
  });

  it("rastavlja primere iz srpskog izdanja", () => {
    expect(syllables("VREMENA")).toBe("VRE-ME-NA");
    expect(syllables("FAMILIJE")).toBe("FA-MI-LI-JE");
    expect(syllables("PRISTAJANJE")).toBe("PRI-STA-JA-NJE");
    expect(syllables("ZNATIŽELJE")).toBe("ZNA-TI-ŽE-LJE");
  });

  it("poštuje suglasničke grupe i samoglasničko R", () => {
    expect(syllables("BESTRAGA")).toBe("BE-STRA-GA");
    expect(syllables("MAJKA")).toBe("MAJ-KA");
    expect(syllables("SRPSKI")).toBe("SRP-SKI");
    expect(syllables("PUCNJAVU")).toBe("PUC-NJA-VU");
    expect(syllables("TRENUTKU")).toBe("TRE-NUT-KU");
    expect(syllables("OKRUGLO")).toBe("OKRU-GLO"); // O-KRU-GLO, ali ne ostavlja samo „O"
  });

  it("ne ostavlja jedno slovo na kraju ili početku reda", () => {
    expect(syllables("OKO")).toBe("OKO");
    expect(hyphenationPoints("IDEMO")).toEqual([3]); // I-DE-MO: prvo mesto bi ostavilo samo „I"
    expect(syllables("NE")).toBe("NE");
  });

  it("ne rastavlja brojeve i skraćenice sa tačkom", () => {
    expect(hyphenationPoints("450")).toEqual([]);
    expect(hyphenationPoints("DIN.")).toEqual([]);
  });

  it("bira najduži deo koji staje i čuva interpunkciju", () => {
    const fits = (text: string) => text.length <= 6;

    expect(splitToFit("TRENUTKU,", fits)).toEqual(["TRE-", "NUTKU,"]); // TRENUT- ima 7 znakova
    expect(splitToFit("PORUKOM!", (text) => text.length <= 5)).toEqual(["PORU-", "KOM!"]);
    expect(splitToFit("OKO", fits)).toBeNull();
  });
});
