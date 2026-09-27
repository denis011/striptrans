// Naglašen tekst (kao u srpskim izdanjima: podebljano i ukošeno): ceo blok ili deo prevoda između zvezdica,
// npr. „REKAO JE TO KRALJICI *LARI*, KAD…". Zvezdica na početku reči otvara naglasak, a na kraju reči
// ga zatvara, pa se svaki red (i deo rastavljene reči) čita sam za sebe, bez stanja iz prethodnog reda.

import type { Measure } from "./layout";

export const MARK = "*";
export const EMPHASIS_BOLD = 0.05; // podebljanje: debljina poteza i dodatni razmak slova, u veličinama slova
export const EMPHASIS_SKEW = 10; // nagib naglašenih slova, u stepenima (varijanta E, izbor korisnika)
export const ITALIC_SKEW = 10; // nagib ukošene naracije (bez podebljanja)
// ukošena slova vire desno od poslednjeg slova dela: visina slova × tangens nagiba, u veličinama slova
const SLANT_OVERHANG = 0.7 * Math.tan((EMPHASIS_SKEW * Math.PI) / 180);

export interface Run {
  text: string;
  emphasis: boolean;
}

const WORD_CHAR = /[\p{L}\p{N}!?.,:;…”"'\-)\]]/u;

/** Zvezdica zatvara naglasak kad stoji odmah posle reči (i posle nje nema slova), inače ga otvara. */
function closes(text: string, index: number): boolean {
  const before = text[index - 1];
  const after = text[index + 1];
  return before !== undefined && WORD_CHAR.test(before) && (after === undefined || !/[\p{L}\p{N}]/u.test(after));
}

/** Delovi reda: običan i naglašen tekst, bez zvezdica. Zvezdica bez para važi do kraja (ili od početka) reda. */
export function splitRuns(line: string): Run[] {
  const marks = [...line.matchAll(/\*/g)].map((match) => match.index!);
  if (marks.length === 0) return line ? [{ text: line, emphasis: false }] : [];
  const runs: Run[] = [];
  let emphasis = closes(line, marks[0]); // prvo zatvaranje: naglasak je počeo u prethodnom redu
  let start = 0;
  for (const index of marks) {
    if (index > start) runs.push({ text: line.slice(start, index), emphasis });
    emphasis = !closes(line, index);
    start = index + 1;
  }
  if (start < line.length) runs.push({ text: line.slice(start), emphasis });
  // susedni delovi istog izgleda se spajaju (npr. „*A* *B*")
  return runs.reduce<Run[]>((merged, run) => {
    const last = merged[merged.length - 1];
    if (last && last.emphasis === run.emphasis) last.text += run.text;
    else merged.push({ ...run });
    return merged;
  }, []);
}

export function stripMarks(text: string): string {
  return text.replaceAll(MARK, "");
}

export function hasMarks(text: string): boolean {
  return text.includes(MARK);
}

/**
 * Širina naglašenog dela: podebljanje širi svako slovo. Ukošen kraj malo viri desno, ali to se računa
 * samo kad se proverava da li red staje (`slant`), a ne u razmaku do sledećeg dela reda („*ORLA*!").
 */
export function runWidth(run: Run, measure: Measure, slant = true): number {
  const base = measure(run.text);
  if (!run.emphasis) return base;
  return base + [...run.text].length * EMPHASIS_BOLD + (slant ? SLANT_OVERHANG : 0);
}

/**
 * Merenje reda sa naglaskom: zvezdice nemaju širinu, a naglašen tekst je malo širi. Sa `all` je ceo
 * tekst naglašen (prekidač „Naglašeno" na bloku). Bez naglaska vraća isto merenje kao pre.
 */
export function emphasisMeasure(measure: Measure, all = false): Measure {
  return (text: string) => {
    if (all) return runWidth({ text: stripMarks(text), emphasis: true }, measure);
    if (!hasMarks(text)) return measure(text);
    return splitRuns(text).reduce((sum, run) => sum + runWidth(run, measure), 0);
  };
}

export interface Edit {
  text: string;
  start: number;
  end: number;
}

/**
 * Dugme B i Ctrl+B: označen tekst (ili reč na kojoj je kursor) dobija zvezdice oko sebe, a već
 * naglašen ih gubi. Razmaci na krajevima izbora ostaju van zvezdica, da oznaka stoji uz reč.
 */
export function toggleEmphasis(text: string, start: number, end: number): Edit {
  if (start === end) {
    // bez izbora: cela reč oko kursora (sa zvezdicama, ako ih ima)
    while (start > 0 && !/\s/.test(text[start - 1])) start -= 1;
    while (end < text.length && !/\s/.test(text[end])) end += 1;
  }
  while (start < end && /\s/.test(text[start])) start += 1;
  while (end > start && /\s/.test(text[end - 1])) end -= 1;
  if (start === end) return { text, start, end };
  const inner = text.slice(start, end);
  // interpunkcija na kraju reči ostaje van naglaska („*ORLA*!"), osim ako je izabran samo znak
  const trailing = /[!?.,:;…]+$/.exec(inner)?.[0] ?? "";
  const core = trailing.length < inner.length ? inner.slice(0, inner.length - trailing.length) : inner;
  const rest = inner.slice(core.length);
  // već naglašeno: zvezdice unutar izbora ili odmah oko njega se skidaju
  if (core.length > 1 && core.startsWith(MARK) && core.endsWith(MARK)) {
    const plain = core.slice(1, -1) + rest;
    return { text: text.slice(0, start) + plain + text.slice(end), start, end: start + plain.length };
  }
  if (text[start - 1] === MARK && text[end] === MARK) {
    return { text: text.slice(0, start - 1) + inner + text.slice(end + 1), start: start - 1, end: end - 1 };
  }
  const marked = `${MARK}${core}${MARK}${rest}`;
  return { text: text.slice(0, start) + marked + text.slice(end), start, end: start + marked.length };
}
