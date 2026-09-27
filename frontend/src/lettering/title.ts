// Naslov od slova originala (Faza 6a): prevod se slaže od slika slova isečenih iz originala,
// sa razmakom, osnovnom linijom i visinom originala, kao što su izdavači radili u Photoshopu.

import type { LetteringStyle, TitleGlyph, TitleGlyphs } from "../api";

export interface TitleLetter {
  index: number; // redni broj slova u prevodu (bez razmaka), ključ za ručne izmene
  key: string; // izabran primerak slova
  char: string;
  source: TitleGlyph["source"];
  x: number; // slika slova na stranici
  y: number;
  width: number;
  height: number;
  rotation: number; // stepeni, oko sredine slova
  fill: boolean; // slovo ima ispunu (unutrašnjost šupljeg slova)
}

export interface TitleLayout {
  letters: TitleLetter[];
  missing: string[]; // znakovi za koje nema slike (preskočeni)
  scale: number;
  x: number; // okvir složenog naslova
  y: number;
  width: number;
  height: number;
}

const LINE_GAP = 0.25; // razmak redova, u visinama slova

/** Primerci jednog slova: slova originala, sastavljena od delova, pa dopunjena (akcenat, rezerva). */
export function choicesFor(title: TitleGlyphs, char: string): TitleGlyph[] {
  return [...title.glyphs, ...(title.custom ?? []), ...title.extra].filter((glyph) => glyph.char === char);
}

interface Placed {
  glyph: TitleGlyph;
  index: number;
  ink: number; // levi kraj mastila u redu, pre uvećanja
}

export function composeTitle(text: string, title: TitleGlyphs, style: LetteringStyle): TitleLayout {
  const byKey = new Map([...title.glyphs, ...(title.custom ?? []), ...title.extra].map((glyph) => [glyph.key, glyph]));
  const order = new Map(title.glyphs.map((glyph, i) => [glyph.key, i]));
  const used = new Map<string, number>();
  const missing: string[] = [];
  const spacing = style.letter_spacing * title.cap_height;

  const pick = (char: string, previous: TitleGlyph | null): TitleGlyph | undefined => {
    // sused iz originala ostaje sused (prva tri slova naslova zadržavaju isti preklop)
    const next = previous && order.has(previous.key) ? title.glyphs[order.get(previous.key)! + 1] : undefined;
    if (next?.char === char && next.row === previous?.row) return next;
    // ponovljeno slovo uzima redom različite primerke originala
    const originals = title.glyphs.filter((glyph) => glyph.char === char);
    if (originals.length) return [...originals].sort((a, b) => (used.get(a.key) ?? 0) - (used.get(b.key) ?? 0))[0];
    // slovo sastavljeno od delova ima prednost nad automatski napravljenim
    return (title.custom ?? []).find((glyph) => glyph.char === char) ?? title.extra.find((glyph) => glyph.char === char);
  };

  const gapBetween = (a: TitleGlyph, b: TitleGlyph) => {
    const i = order.get(a.key);
    const j = order.get(b.key);
    return i !== undefined && j === i + 1 && a.gap_next != null ? a.gap_next : title.gap;
  };

  let index = 0;
  const lines = text
    .toUpperCase()
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const placed: Placed[] = [];
      let previous: TitleGlyph | null = null;
      let space = false;
      let cursor = 0;
      for (const char of line) {
        if (char === " ") {
          space = placed.length > 0;
          continue;
        }
        const chosen = style.letters[String(index)]?.key;
        const own = chosen ? byKey.get(chosen) : undefined;
        const glyph: TitleGlyph | undefined = own?.char === char ? own : pick(char, previous);
        if (!glyph) {
          missing.push(char);
          index += 1;
          continue;
        }
        if (previous) cursor += (space ? title.word_gap : gapBetween(previous, glyph)) + spacing;
        placed.push({ glyph, index, ink: cursor });
        cursor += glyph.ink_right - glyph.ink_left;
        used.set(glyph.key, (used.get(glyph.key) ?? 0) + 1);
        previous = glyph;
        space = false;
        index += 1;
      }
      return { placed, width: cursor };
    });

  const widest = Math.max(1, ...lines.map((line) => line.width));
  const fill = style.fit === "fill" ? Math.min((title.right - title.left) / widest, title.max_scale) : 1;
  const scale = fill * style.scale;
  const unit = title.cap_height * scale;
  const total = lines.length * unit + Math.max(0, lines.length - 1) * LINE_GAP * unit;
  const centerX = (title.left + title.right) / 2;
  const centerY = (title.top + title.bottom) / 2;
  const letters: TitleLetter[] = lines.flatMap((line, row) => {
    const baseline = centerY - total / 2 + unit * (row + 1) + LINE_GAP * unit * row;
    const start = centerX - (line.width * scale) / 2;
    return line.placed.map(({ glyph, index: letterIndex, ink }) => {
      const nudge = style.letters[String(letterIndex)];
      return {
        index: letterIndex,
        key: glyph.key,
        char: glyph.char,
        source: glyph.source,
        x: start + (ink - glyph.ink_left) * scale + (nudge?.dx ?? 0) * unit,
        y: baseline - glyph.baseline * scale + (nudge?.dy ?? 0) * unit,
        width: glyph.width * scale,
        height: glyph.height * scale,
        rotation: nudge?.rotation ?? 0,
        fill: !!glyph.fill,
      };
    });
  });
  if (!letters.length) {
    return { letters, missing, scale, x: centerX, y: centerY, width: 0, height: 0 };
  }
  const left = Math.min(...letters.map((letter) => letter.x));
  const top = Math.min(...letters.map((letter) => letter.y));
  const right = Math.max(...letters.map((letter) => letter.x + letter.width));
  const bottom = Math.max(...letters.map((letter) => letter.y + letter.height));
  return { letters, missing, scale, x: left, y: top, width: right - left, height: bottom - top };
}
