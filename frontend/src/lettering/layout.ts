// Slaganje prevoda u oblačić: veličina slova kao u originalu, redovi po obliku oblačića, rastavljanje.
// Sve je čista računica nad funkcijom `measure`, pa se isti kod koristi za prikaz i za izvoz.

import { splitToFit } from "./hyphenate";

/** Širina teksta u pikselima pri veličini slova 1. */
export type Measure = (text: string) => number;

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Placement {
  x: number;
  y: number;
  width: number; // red se centrira u ovoj širini
}

export interface Layout {
  lines: string[];
  placements: Placement[]; // položaj svakog reda
  size: number; // veličina slova u pikselima stranice
  lineHeight: number; // množilac veličine slova
  x: number;
  y: number;
  width: number;
  height: number;
  fits: boolean; // false: tekst ne staje ni najmanjim dozvoljenim slovima
  // zašto ne staje: najširi red i koliko px mu nedostaje (bez toga je problem u visini)
  overflow?: { line: number; extra: number } | null;
}

export interface LayoutOptions {
  pitch: number; // razmak redova originala na stranici (px)
  capRatio: number; // visina velikog slova fonta / veličina slova
  shape: "bubble" | "rect";
  // izmeren beli prostor oblačića (poligon: levi rub odozgo, pa desni odozdo); bez njega elipsa u okviru
  outline?: number[][] | null;
  scale?: number; // ručna veličina (udeo automatske); tada se slova ne smanjuju sama
  lineSpacing?: number; // prored u odnosu na original
  align?: "left" | "center" | "right" | "justify"; // levo i desno poravnanje traže zajedničku ivicu
}

export const CAP_TO_PITCH = 0.6; // izmereno na skenovima (IT 0,62, SR 0,57)
const MIN_SCALE = 0.75; // slova se smanjuju najviše na 3/4 veličine originala
const GROW_WIDTH = 0.15; // okvir originala sme da se proširi, jer je oblačić veći od teksta
const GROW_HEIGHT = 0.35;
const BUBBLE_CURVE = 0.8; // koliko su gornji i donji red uži od srednjeg
const HYPHENATE_BELOW = 0.75; // reč se rastavlja samo ako bi red ostao popunjen manje od 3/4
const PADDING = 0.3; // razmak teksta od ivice oblačića, u razmacima redova
const BAND_MARGIN = 0.1; // pojas reda koji mora biti u oblačiću: visina slova ± ovoliko
// naracija ima sitnija slova od govora: blok sa bar dva reda koristi svoj razmak, ali blizu stranicinog
const PITCH_MIN = 0.7;
const PITCH_MAX = 1.4;

/** Širine redova (udeo pune širine) za n redova: u oblačiću srednji redovi su najširi. */
export function lineProfile(count: number, shape: LayoutOptions["shape"]): number[] {
  return Array.from({ length: count }, (_, i) => {
    if (shape === "rect" || count === 1) return 1;
    const t = ((i + 0.5) / count) * 2 - 1;
    return Math.sqrt(1 - (t * BUBBLE_CURVE) ** 2);
  });
}

/** Pohlepno punjenje redova zadatih širina, uz rastavljanje; null ako tekst ne staje. */
export function breakLines(words: string[], widths: number[], size: number, measure: Measure, hyphenate = true): string[] | null {
  const width = (text: string) => measure(text) * size;
  const queue = [...words];
  const lines: string[] = [];
  let current = "";
  while (queue.length > 0) {
    if (lines.length >= widths.length) return null;
    const limit = widths[lines.length];
    const word = queue.shift() as string;
    const candidate = current ? `${current} ${word}` : word;
    if (width(candidate) <= limit) {
      current = candidate;
      continue;
    }
    const filled = current ? width(current) / limit : 0;
    const split = hyphenate && filled < HYPHENATE_BELOW ? splitToFit(word, (head) => width(current ? `${current} ${head}` : head) <= limit) : null;
    if (split) {
      lines.push(current ? `${current} ${split[0]}` : split[0]);
      queue.unshift(split[1]);
      current = "";
      continue;
    }
    if (!current) return null; // ni sama reč ne staje u red
    lines.push(current);
    current = "";
    queue.unshift(word);
  }
  if (current) lines.push(current);
  return lines.length <= widths.length ? lines : null;
}

/** Brojevi redova za probu: prvo koliko je imao original (sličan oblik teksta), pa susedni. */
export function lineCounts(original: number, max: number): number[] {
  const counts: number[] = [];
  for (let distance = 0; counts.length < max && distance <= original + max; distance += 1) {
    for (const count of distance === 0 ? [original] : [original - distance, original + distance]) {
      if (count >= 1 && count <= max && !counts.includes(count)) counts.push(count);
    }
  }
  return counts;
}

interface Slot {
  center: number;
  width: number;
}

interface Outline {
  ys: number[];
  lefts: number[];
  rights: number[];
}

const MIN_OUTLINE_ROWS = 3;
// izmeren oblik mnogo manji od bloka je promašaj merenja (uhvaćen samo deo belog), pa se ne koristi;
// na ~1170 oblačića iz dva broja oblik je skoro uvek 1,0–1,3 visine bloka; ispod 0,7 su samo
// promašaji (npr. 0,54: obod šešira ulazi u oblačić, pa merenje staje na pola)
const OUTLINE_MIN = 0.7;

/**
 * Izmeren oblik oblačića (levi rub odozgo, pa desni odozdo, isti redovi). Pravougaonik koji upiše detektor
 * (4 tačke) ili pokvaren oblik se ne koristi: tada važi elipsa u okviru bloka.
 */
export function readOutline(points: number[][] | null | undefined): Outline | null {
  if (!points || points.length < MIN_OUTLINE_ROWS * 2 || points.length % 2) return null;
  const half = points.length / 2;
  const left = points.slice(0, half);
  const right = points.slice(half).reverse();
  const ys = left.map((p) => p[1]);
  const rising = ys.every((y, i) => i === 0 || y > ys[i - 1]);
  const paired = right.every((p, i) => p[1] === ys[i] && p[0] >= left[i][0]);
  if (!rising || !paired) return null;
  return { ys, lefts: left.map((p) => p[0]), rights: right.map((p) => p[0]) };
}

/** Izmeren oblik se odbacuje ako je mnogo manji od bloka: tada važi elipsa u okviru bloka. */
export function usableOutline(outline: Outline | null, box: Box): Outline | null {
  if (!outline) return null;
  const height = outline.ys[outline.ys.length - 1] - outline.ys[0];
  const width = Math.max(...outline.rights.map((right, i) => right - outline.lefts[i]));
  return height >= OUTLINE_MIN * box.height && width >= OUTLINE_MIN * box.width ? outline : null;
}

/** Najuži deo oblačića u pojasu [top, bottom]; null ako pojas izlazi iz izmerenog oblika. */
function spanAt(outline: Outline, top: number, bottom: number): [number, number] | null {
  const { ys, lefts, rights } = outline;
  if (top < ys[0] || bottom > ys[ys.length - 1]) return null;
  let left = -Infinity;
  let right = Infinity;
  ys.forEach((y, i) => {
    if (y >= top && y <= bottom) {
      left = Math.max(left, lefts[i]);
      right = Math.min(right, rights[i]);
    }
  });
  if (left === -Infinity) {
    const nearest = ys.reduce((best, y, i) => (Math.abs(y - (top + bottom) / 2) < Math.abs(ys[best] - (top + bottom) / 2) ? i : best), 0);
    return [lefts[nearest], rights[nearest]];
  }
  return [left, right];
}

/**
 * Ravnomerni redovi: najuže širine (isti udeo svake) u koje tekst još staje u zadati broj redova.
 * Pohlepno punjenje bi dalo dugačak prvi i kratak poslednji red; letteristi raspoređuju ravnomerno.
 */
export function balancedLines(words: string[], widths: number[], size: number, measure: Measure): string[] | null {
  // rastavljanje reči samo kad bez njega tekst ne staje (čitljivije, a imena ostaju cela)
  const hyphenate = breakLines(words, widths, size, measure, false) === null;
  let best = breakLines(words, widths, size, measure, hyphenate);
  if (!best) return null;
  let low = 0.3;
  let high = 1;
  for (let i = 0; i < 10; i += 1) {
    const share = (low + high) / 2;
    const lines = breakLines(
      words,
      widths.map((width) => width * share),
      size,
      measure,
      hyphenate,
    );
    if (lines) {
      best = lines;
      high = share;
    } else {
      low = share;
    }
  }
  return best;
}

/** Složi tekst u okvir bloka; okvir se po potrebi malo proširi, a slova smanje tek na kraju. */
export function layoutText(text: string, box: Box, measure: Measure, options: LayoutOptions): Layout {
  const words = text.trim().split(/\s+/).filter(Boolean);
  // ručni prelomi: korisnik je sam rasporedio redove (Enter u prevodu)
  const manual = text.includes("\n") ? text.split("\n").map((line) => line.trim().split(/\s+/).join(" ")).filter(Boolean) : null;
  const baseSize = (CAP_TO_PITCH * options.pitch) / options.capRatio;
  const lineHeight = (options.pitch / baseSize) * (options.lineSpacing ?? 1);
  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  const outline = usableOutline(readOutline(options.outline), box);

  /**
   * Vrh prvog reda: tekst stoji u sredini bloka, ali se uvlači u izmereni oblačić kad je oblačić
   * pomeren u odnosu na okvir (detektor ga je zahvatio malo više ili niže nego što je beli prostor).
   */
  const bandTop = (count: number, size: number): number => {
    const height = count * size * lineHeight;
    const top = centerY - height / 2;
    if (!outline) return top;
    const first = outline.ys[0];
    const last = outline.ys[outline.ys.length - 1];
    if (last - first < height) return top; // oblačić je niži od teksta: pomeranje ne pomaže
    return Math.min(Math.max(top, first), last - height);
  };

  const slotsFor = (count: number, size: number, widen: number): Slot[] | null => {
    const step = size * lineHeight;
    if (!outline) {
      const width = box.width * (1 + widen * GROW_WIDTH);
      return lineProfile(count, options.shape).map((share) => ({ center: centerX, width: share * width }));
    }
    const top = bandTop(count, size);
    const cap = CAP_TO_PITCH * options.pitch * (size / baseSize);
    const margin = BAND_MARGIN * options.pitch;
    const pad = PADDING * options.pitch;
    const slots: Slot[] = [];
    for (let i = 0; i < count; i += 1) {
      const middle = top + (i + 0.5) * step;
      const span = spanAt(outline, middle - cap / 2 - margin, middle + cap / 2 + margin);
      if (!span || span[1] - span[0] - 2 * pad <= 0) return null;
      slots.push({ center: (span[0] + span[1]) / 2, width: span[1] - span[0] - 2 * pad });
    }
    return slots;
  };

  /**
   * Levo (i desno) poravnanje: svi redovi počinju na istoj ivici, iako su im mesta u oblačiću
   * različito široka. Red koji tako ne bi stao ostaje u svom mestu, da ne izađe iz oblačića.
   */
  const shareEdges = (lines: string[], placements: Placement[], size: number): Placement[] => {
    const align = options.align;
    if (!align || align === "center" || placements.length < 2) return placements;
    const widths = lines.map((line) => measure(line) * size);
    let result = placements;
    if (align === "left" || align === "justify") {
      const left = Math.max(...result.map((item) => item.x));
      result = result.map((item, i) => {
        const x = Math.max(item.x, Math.min(left, item.x + item.width - widths[i]));
        return { ...item, x, width: item.width - (x - item.x) };
      });
    }
    if (align === "right" || align === "justify") {
      const right = Math.min(...result.map((item) => item.x + item.width));
      result = result.map((item, i) => ({
        ...item,
        width: Math.min(item.width, Math.max(right, item.x + widths[i]) - item.x),
      }));
    }
    return result;
  };

  /** `limits` su prava mesta u oblačiću: kad tekst ne staje, crta se šire, ali poruka meri prema njima. */
  const place = (
    lines: string[],
    slots: Slot[],
    size: number,
    fits: boolean,
    limits?: Slot[] | null,
  ): Layout => {
    const step = size * lineHeight;
    const top = bandTop(lines.length, size);
    const placements = shareEdges(
      lines,
      lines.map((_, i) => {
        const slot = slots[Math.min(i, slots.length - 1)];
        return { x: slot.center - slot.width / 2, y: top + i * step, width: slot.width };
      }),
      size,
    );
    const left = Math.min(...placements.map((item) => item.x), centerX);
    const right = Math.max(...placements.map((item) => item.x + item.width), centerX);
    // koji red je preširok i koliko: panel to kaže korisniku, da zna šta da promeni
    const room = (index: number) =>
      limits ? limits[Math.min(index, limits.length - 1)].width : placements[index].width;
    const wide = lines
      .map((line, i) => ({ line: i + 1, extra: measure(line) * size - room(i) }))
      .sort((a, b) => b.extra - a.extra)[0];
    const overflow = !fits && wide && wide.extra > 0 ? { line: wide.line, extra: Math.round(wide.extra) } : null;
    return { lines, placements, size, lineHeight, x: left, y: top, width: right - left, height: lines.length * step, fits, overflow };
  };
  if (words.length === 0) return place([], [], baseSize, true);

  /** Tekst u `count` redova date veličine; ako stane u manje redova, položaji se računaju za toliko. */
  const fit = (count: number, size: number, widen: number): Layout | null => {
    const slots = slotsFor(count, size, widen);
    if (!slots) return null;
    const lines = balancedLines(
      words,
      slots.map((slot) => slot.width),
      size,
      measure,
    );
    if (!lines) return null;
    if (lines.length === count) return place(lines, slots, size, true);
    const fewer = slotsFor(lines.length, size, widen);
    if (fewer && lines.every((line, i) => measure(line) * size <= fewer[i].width + 1e-6)) return place(lines, fewer, size, true);
    return null;
  };

  const scales = Array.from({ length: Math.round((1 - MIN_SCALE) / 0.05) + 1 }, (_, i) => 1 - i * 0.05);
  const fixedScale = options.scale !== undefined && options.scale !== 1 ? options.scale : null;
  if (manual || fixedScale !== null) {
    // ručno podešeno: veličina se ne menja sama, samo se proverava da li staje
    const size = baseSize * (fixedScale ?? 1);
    if (manual) {
      // ručni prelomi ostaju, ali slova smeju da se smanje da bi redovi stali (osim ako je veličina zadata)
      const sizes = fixedScale !== null ? [size] : scales.map((scale) => baseSize * scale);
      for (const trial of sizes) {
        const slots = slotsFor(manual.length, trial, 0);
        if (slots && manual.every((line, i) => measure(line) * trial <= slots[i].width + 1e-6)) {
          return place(manual, slots, trial, true);
        }
      }
      // Enter je obavezan prelom, a ne ceo raspored: deo koji ne staje u svoj red prelama se dalje sam
      // (npr. samo jedan prelom posle „ZAR ZAISTA", a ostatak rečenice se složi kao i inače)
      const flow = (widths: number[], trial: number): string[] | null => {
        const lines: string[] = [];
        for (const segment of manual) {
          const broken = breakLines(segment.split(" "), widths.slice(lines.length), trial, measure);
          if (!broken) return null;
          lines.push(...broken);
        }
        return lines;
      };
      const room = Math.max(box.height * (1 + GROW_HEIGHT), box.height + options.pitch, outline ? outline.ys[outline.ys.length - 1] - outline.ys[0] : 0);
      // samo deo koji ne bi stao ni u celu širinu oblačića nije raspoređen rukom; ručno raspoređeni redovi
      // se nikad ne prelamaju (red koji ne staje ostaje crven, a panel kaže koji je)
      const widest = box.width * (1 + GROW_WIDTH);
      const unplaced = manual.some((line) => measure(line) * sizes[sizes.length - 1] > widest);
      for (const trial of unplaced ? sizes : []) {
        const most = Math.max(manual.length, Math.floor(room / (trial * lineHeight) + 1e-9));
        for (let count = manual.length + 1; count <= most; count += 1) {
          const slots = slotsFor(count, trial, 0);
          const lines = slots && flow(slots.map((slot) => slot.width), trial);
          if (!slots || !lines) continue;
          if (lines.length === count) return place(lines, slots, trial, true);
          const fewer = slotsFor(lines.length, trial, 0);
          if (fewer && lines.every((line, i) => measure(line) * trial <= fewer[i].width + 1e-6)) return place(lines, fewer, trial, true);
        }
      }
      const slots = slotsFor(manual.length, size, 0) ?? slotsFor(manual.length, size, 1);
      const fallback = [{ center: centerX, width: Math.max(...manual.map((line) => measure(line) * size)) }];
      return place(manual, slots ?? fallback, size, false, slots);
    }
    const maxLines = Math.max(1, Math.floor(Math.max(box.height + options.pitch * 2, outline ? outline.ys[outline.ys.length - 1] - outline.ys[0] : 0) / (size * lineHeight)));
    for (const count of lineCounts(Math.max(1, Math.round(box.height / options.pitch)), maxLines)) {
      const fitted = fit(count, size, 0);
      if (fitted) return fitted;
    }
    const width = box.width * (1 + GROW_WIDTH);
    const lines = breakLines(words, Array(words.length * 2).fill(width), size, measure) ?? words;
    return place(lines, [{ center: centerX, width }], size, false, slotsFor(lines.length, size, 0));
  }

  // redosled pokušaja: dodaj red (oblačić je viši od teksta), pa smanji slova; u širinu tek na kraju,
  // jer širi red najlakše izađe iz oblačića (sa izmerenim oblikom širenje nema smisla)
  const extraHeight = Math.max(box.height * GROW_HEIGHT, options.pitch);
  const originalLines = Math.max(1, Math.round(box.height / options.pitch));
  const outlineHeight = outline ? outline.ys[outline.ys.length - 1] - outline.ys[0] : 0;
  const attempts = [
    ...scales.flatMap((scale) => [0, 0.5, 1].map((grow) => ({ scale, grow, widen: 0 }))),
    ...(outline ? [] : scales.map((scale) => ({ scale, grow: 1, widen: 1 }))),
  ];
  for (const { scale, grow, widen } of attempts) {
    const size = baseSize * scale;
    const height = Math.max(box.height + grow * extraHeight, grow === 1 ? outlineHeight : 0);
    const maxLines = Math.max(1, Math.floor(height / (size * lineHeight) + 1e-9));
    for (const count of lineCounts(originalLines, maxLines)) {
      const fitted = fit(count, size, widen);
      if (fitted) return fitted;
    }
  }
  // ne staje ni najmanjim slovima: složi u širinu proširenog okvira, bez ograničenja broja redova
  const size = baseSize * MIN_SCALE;
  const width = box.width * (1 + GROW_WIDTH);
  const lines = breakLines(words, Array(words.length * 2).fill(width), size, measure) ?? words;
  return place(lines, [{ center: centerX, width }], size, false, slotsFor(lines.length, size, 0));
}

const BOX_PADDING = 0.02; // unutrašnja margina okvira, u delovima kraće strane
const BOX_LINE_HEIGHT = 1.15; // prored običnog teksta (množilac veličine slova)
const MIN_BOX_SIZE = 6; // sitnije od ovoga se ne čita ni na papiru

export interface BoxOptions {
  lineSpacing?: number;
  scale?: number; // ručna veličina u odnosu na najveću koja staje
}

/**
 * „Uklopi u okvir" (uredničke strane, impresum): tekst se prelama po širini okvira i puni ga, a veličina slova
 * se bira slobodno — najveća sa kojom ceo tekst staje. Prazan red u prevodu je granica pasusa.
 */
export function layoutBox(text: string, box: Box, measure: Measure, options: BoxOptions): Layout {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const pad = Math.min(box.width, box.height) * BOX_PADDING;
  const width = Math.max(1, box.width - 2 * pad);
  const height = Math.max(1, box.height - 2 * pad);
  const lineHeight = BOX_LINE_HEIGHT * (options.lineSpacing ?? 1);

  const wrap = (size: number): string[] | null => {
    const lines: string[] = [];
    for (const [index, paragraph] of paragraphs.entries()) {
      const words = paragraph.split(" ");
      const broken = breakLines(words, Array(words.length * 2).fill(width), size, measure);
      if (!broken) return null; // ni jedna reč ne staje u širinu okvira
      lines.push(...broken);
      if (index < paragraphs.length - 1) lines.push(""); // prazan red između pasusa
    }
    return lines;
  };
  const fitsAt = (size: number) => {
    const lines = wrap(size);
    return lines && lines.length * size * lineHeight <= height + 1e-6 ? lines : null;
  };

  // najveća veličina sa kojom sve staje (binarna pretraga)
  let low = MIN_BOX_SIZE;
  let high = Math.max(MIN_BOX_SIZE, height / lineHeight);
  let best = fitsAt(low);
  for (let i = 0; best && i < 24; i += 1) {
    const middle = (low + high) / 2;
    const lines = fitsAt(middle);
    if (lines) {
      low = middle;
      best = lines;
    } else {
      high = middle;
    }
  }
  const scale = options.scale ?? 1;
  const size = low * scale;
  const lines = scale === 1 && best ? best : (wrap(size) ?? paragraphs);
  const step = size * lineHeight;
  const fits = !!best && lines.length * step <= height + 1e-6 && lines.every((line) => measure(line) * size <= width + 1e-6);
  const top = box.y + pad + Math.max(0, (height - lines.length * step) / 2);
  const placements = lines.map((_, i) => ({ x: box.x + pad, y: top + i * step, width }));
  const widest = lines.reduce((most, line, i) => {
    const extra = measure(line) * size - width;
    return extra > most.extra ? { line: i + 1, extra } : most;
  }, { line: 0, extra: 0 });
  return {
    lines,
    placements,
    size,
    lineHeight,
    x: box.x + pad,
    y: top,
    width,
    height: lines.length * step,
    fits,
    overflow: !fits && widest.extra > 0 ? { line: widest.line, extra: Math.round(widest.extra) } : null,
  };
}

/** Onomatopeja ili natpis: jedan red, što veća slova koja staju u okvir (`fill` = udeo okvira). */
export function layoutSound(text: string, box: Box, measure: Measure, capRatio: number, fill = 0.95): Layout {
  const line = text.trim().split(/\s+/).join(" ");
  const byWidth = line ? box.width / Math.max(measure(line), 1e-6) : box.height;
  const size = Math.min(box.height / Math.max(capRatio, 0.5), byWidth) * fill;
  const height = size * 1.1;
  const y = box.y + box.height / 2 - height / 2;
  return {
    lines: line ? [line] : [],
    placements: line ? [{ x: box.x, y, width: box.width }] : [],
    size,
    lineHeight: 1.1,
    x: box.x,
    y,
    width: box.width,
    height,
    fits: true,
  };
}

/** Razmak redova bloka: sopstveni kad original ima bar dva reda (naracija je sitnija), inače stranicin. */
export function blockPitch(height: number, text: string, pagePitch: number): number {
  const lines = text.split("\n").filter((line) => line.trim()).length;
  if (lines < 2) return pagePitch;
  return Math.min(Math.max(height / lines, pagePitch * PITCH_MIN), pagePitch * PITCH_MAX);
}

const PAGE_LINES = 64; // tipična strana: ~64 reda teksta po visini strane
// medijana zna da odleti kad strana ima malo blokova sa dva reda (naslovna traka, veliki natpis)
const PAGE_PITCH_MIN = 0.7;
const PAGE_PITCH_MAX = 1.5;

/** Razmak redova originala na stranici: medijana visina/broj redova blokova sa bar dva reda. */
export function pagePitch(blocks: { height: number; text: string; kind: string }[], pageHeight: number): number {
  const typical = pageHeight / PAGE_LINES;
  const pitches = blocks
    .filter((block) => block.kind !== "sfx" && block.kind !== "other")
    .map((block) => ({ height: block.height, lines: block.text.split("\n").filter((line) => line.trim()).length }))
    .filter((item) => item.lines >= 2)
    .map((item) => item.height / item.lines)
    .sort((a, b) => a - b);
  if (pitches.length === 0) return typical;
  const median = pitches[Math.floor(pitches.length / 2)];
  return Math.min(Math.max(median, typical * PAGE_PITCH_MIN), typical * PAGE_PITCH_MAX);
}
