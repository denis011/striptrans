// Rastavljanje srpskih reči (latinica, velika slova) na kraju reda, po slogovima.
// LJ, NJ i DŽ se nikad ne razdvajaju; R između suglasnika je samoglasničko (SRP-SKI, PRST).
// Primeri iz srpskih izdanja: VRE-MENA, FA-MILIJE, PRISTA-JANJE, ZNATIŽE-LJE.

const VOWELS = new Set(["A", "E", "I", "O", "U"]);
const DIGRAPHS = ["LJ", "NJ", "DŽ"];
const SIBILANTS = new Set(["S", "Z", "Š", "Ž"]);
// suglasnik + jedan od ovih ide zajedno u sledeći slog (O-KRU-GLO); nazali ne (PUC-NJA-VA, RAD-NIK)
const ONSET_SECOND = new Set(["R", "L", "LJ", "V", "J"]);
const SONANTS = new Set(["R", "L", "LJ", "V", "J", "M", "N", "NJ"]);
const MIN_PART = 2; // najmanje slova na svakoj strani crtice

/** Glasovi reči: digrafi LJ, NJ, DŽ su jedan glas. */
export function units(word: string): string[] {
  const result: string[] = [];
  for (let i = 0; i < word.length; ) {
    const pair = word.slice(i, i + 2);
    if (DIGRAPHS.includes(pair)) {
      result.push(pair);
      i += 2;
    } else {
      result.push(word[i]);
      i += 1;
    }
  }
  return result;
}

function isLetter(unit: string): boolean {
  return /^[A-ZČĆŽŠĐ]+$/.test(unit);
}

function nuclei(parts: string[]): number[] {
  const found: number[] = [];
  parts.forEach((unit, i) => {
    if (VOWELS.has(unit)) {
      found.push(i);
    } else if (unit === "R") {
      // samoglasničko R: između suglasnika ili na početku ispred suglasnika
      const before = parts[i - 1];
      const after = parts[i + 1];
      const consonantBefore = before === undefined || !VOWELS.has(before);
      const consonantAfter = after !== undefined && isLetter(after) && !VOWELS.has(after);
      if (consonantBefore && consonantAfter) found.push(i);
    }
  });
  return found;
}

/** Koliko suglasnika iz grupe između dva sloga ostaje u prvom slogu. */
function stay(cluster: string[]): number {
  if (cluster.length <= 1) return 0; // VO-DA
  if (SIBILANTS.has(cluster[0])) return 0; // SE-STRA, PRI-STA-JA-NJE
  if (cluster.length === 2 && !SONANTS.has(cluster[0]) && ONSET_SECOND.has(cluster[1])) return 0; // O-KRU-GLO
  return 1; // MAJ-KA, SRP-SKI
}

/** Mesta (indeksi u slovima) gde reč sme da se rastavi. */
export function hyphenationPoints(word: string): number[] {
  if (!isLetter(word)) return [];
  const parts = units(word);
  const cores = nuclei(parts);
  const points: number[] = [];
  for (let n = 0; n + 1 < cores.length; n += 1) {
    const cluster = parts.slice(cores[n] + 1, cores[n + 1]);
    const split = cores[n] + 1 + stay(cluster);
    const offset = parts.slice(0, split).join("").length;
    if (offset >= MIN_PART && word.length - offset >= MIN_PART) points.push(offset);
  }
  return points;
}

/** Reč sa crticama na svim dozvoljenim mestima (za testove i proveru). */
export function syllables(word: string): string {
  let result = word;
  for (const point of [...hyphenationPoints(word)].reverse()) result = `${result.slice(0, point)}-${result.slice(point)}`;
  return result;
}

/**
 * Rastavi reč (sa eventualnom interpunkcijom na kraju) tako da prvi deo sa crticom stane u `fits`.
 * Vraća najduži deo koji staje, ili null.
 */
export function splitToFit(token: string, fits: (text: string) => boolean): [string, string] | null {
  // naglašena reč počinje zvezdicom (*BESKORISNO*): rastavlja se isto, a zvezdice ostaju na krajevima
  const match = /^(\*?)([A-ZČĆŽŠĐ]+)(.*)$/.exec(token);
  if (!match) return null;
  const [, mark, word, tail] = match;
  for (const point of [...hyphenationPoints(word)].reverse()) {
    const head = `${mark}${word.slice(0, point)}-`;
    if (fits(head)) return [head, word.slice(point) + tail];
  }
  return null;
}
