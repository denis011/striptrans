// Prevodi blokova stranice pretvoreni u složen tekst za prikaz na canvas-u.

import { AUTO_STYLE, type LetteringStyle, type TextBlock, titleGlyphUrl } from "../api";
import { type Run, emphasisMeasure, hasMarks, runWidth, splitRuns, stripMarks } from "./emphasis";
import type { FontMetrics } from "./fonts";
import { type Layout, blockPitch, layoutBox, layoutSound, layoutText, pagePitch } from "./layout";
import { composeTitle } from "./title";

export interface Lettering {
  id: number;
  layout: Layout;
  family: string;
  outline: boolean; // onomatopeja: obrub oko slova, da se odvoje od crteža
  light: boolean; // tamna podloga (naslov belim slovima na crnom): svetla slova
  words: (JustifiedWord[] | null)[] | null; // obostrano poravnanje: položaj svake reči u redu
  style: LetteringStyle;
  center: { x: number; y: number }; // oko ove tačke se tekst rotira (pre pomeraja)
  images?: LetterImage[]; // naslov: slike slova originala umesto teksta
  tilt?: number; // kos naslov: ugao reda originala (stepeni), dodaje se ručnoj rotaciji
  skew?: number; // kos naslov u kurzivu: nagib slova (tangens)
  // naglasak ili ukošena naracija: delovi svakog reda sa položajem; null = redovi se crtaju celi (kao pre)
  runs?: (PlacedRun[] | null)[] | null;
  italic?: boolean; // ukošena naracija (opcija serijala)
}

export interface PlacedRun extends Run {
  x: number; // levi kraj dela na stranici
}

export interface LetterImage {
  url: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number; // stepeni, oko sredine slike
}

const BUBBLE_KINDS = new Set(["speech", "thought", "caption"]);
const SOUND_FILL = 0.95; // onomatopeja popunjava okvir kao original
const SIGN_FILL = 0.75; // natpis na tabli ostavlja rub table
const normalized = (text: string) => text.toUpperCase().replace(/[^A-ZČĆŽŠĐ0-9]/g, "");

/** Da li se prevod bloka slaže na slici (isto pravilo kao brisanje originala na backendu). */
export function isLettered(block: TextBlock): boolean {
  if (!block.translation.trim()) return false;
  if (BUBBLE_KINDS.has(block.kind)) return true;
  // natpis, naslov ili onomatopeja: samo kad je preveden drugačije od originala (tada je original obrisan)
  return normalized(block.translation) !== normalized(block.text);
}

/** Stil bloka: automatski (sa nagibom originalne onomatopeje) + ručne korekcije. */
export function blockStyle(block: TextBlock): LetteringStyle {
  return { ...AUTO_STYLE, rotation: block.kind === "sfx" ? (block.angle ?? 0) : 0, ...block.style };
}

export interface JustifiedWord {
  text: string;
  x: number; // levi kraj reči na stranici
}

/**
 * Obostrano poravnanje: redovi se razvlače do širine najšireg reda (ali ne preko svog mesta u oblačiću);
 * poslednji red i red sa jednom reči ostaju centrirani, kao što je običaj u stripu.
 */
export function justifyLines(layout: Layout, measure: (text: string) => number): (JustifiedWord[] | null)[] {
  const widths = layout.lines.map((line) => measure(line) * layout.size);
  const target = Math.max(...widths);
  return layout.lines.map((line, index) => {
    const words = line.split(" ");
    // poslednji red pasusa (pre praznog reda ili na kraju) ostaje neraširen
    const paragraphEnd = index === layout.lines.length - 1 || layout.lines[index + 1] === "";
    if (paragraphEnd || words.length < 2) return null;
    const placement = layout.placements[index];
    const width = Math.min(target, placement.width);
    const wordWidths = words.map((word) => measure(word) * layout.size);
    const gap = (width - wordWidths.reduce((sum, value) => sum + value, 0)) / (words.length - 1);
    let x = placement.x + (placement.width - width) / 2;
    return words.map((word, i) => {
      const result = { text: word, x };
      x += wordWidths[i] + gap;
      return result;
    });
  });
}

export interface PageFonts {
  dialogue: FontMetrics;
  sound: FontMetrics;
  byKey: (key: string) => FontMetrics | undefined; // font zadat samo za jedan blok
  captionItalic?: boolean; // opcija serijala: naracija ukošena (kao u srpskim izdanjima)
}

/** Delovi jednog reda (ili reči, kod obostranog) poređani od `x`, širinama iz merenja sa naglaskom. */
function placeRuns(text: string, x: number, all: boolean, size: number, measure: FontMetrics["measure"]): PlacedRun[] {
  const runs = all ? [{ text: stripMarks(text), emphasis: true }] : splitRuns(text);
  return runs.map((run) => {
    const placed = { ...run, x };
    x += runWidth(run, measure, false) * size;
    return placed;
  });
}

/**
 * Položaji delova redova kad blok ima naglasak (ceo ili zvezdicama) ili je ukošena naracija; inače null,
 * pa se redovi crtaju kao pre. Poravnanje se računa istim merenjem kojim je tekst složen.
 */
export function lineRuns(
  layout: Layout,
  measure: FontMetrics["measure"],
  align: LetteringStyle["align"],
  words: (JustifiedWord[] | null)[] | null,
  all: boolean,
  italic: boolean,
): (PlacedRun[] | null)[] | null {
  if (!all && !italic && !layout.lines.some(hasMarks)) return null;
  const measured = emphasisMeasure(measure, all);
  const side = align === "justify" ? "center" : align;
  return layout.lines.map((line, index) => {
    if (!line) return null;
    const spread = words?.[index];
    if (spread) return spread.flatMap((word) => placeRuns(word.text, word.x, all, layout.size, measure));
    const placement = layout.placements[index];
    const width = measured(line) * layout.size;
    const x = { left: placement.x, center: placement.x + (placement.width - width) / 2, right: placement.x + placement.width - width }[side];
    return placeRuns(line, x, all, layout.size, measure);
  });
}

export function letterBlocks(blocks: TextBlock[], pageHeight: number, fonts: PageFonts): Lettering[] {
  const pitch = pagePitch(blocks, pageHeight);
  return blocks
    .filter(isLettered)
    .map((block) => {
      const style = blockStyle(block);
      if (block.kind === "title" && block.title?.glyphs.length) return titleLettering(block, style);
      const box = { x: block.x, y: block.y, width: block.width, height: block.height };
      const sound = block.kind === "sfx";
      const font = (style.font && fonts.byKey(style.font)) || (sound ? fonts.sound : fonts.dialogue);
      // onomatopeja, natpis i naslov bez isečenih slova: jedan red preko celog okvira; ručna
      // veličina ga uvećava ili smanjuje
      const fitted = sound || block.kind === "other" || block.kind === "title";
      // naglasak važi za oblačiće i naraciju; onomatopeja i natpis se slažu kao pre (zvezdice se ne crtaju)
      const all = !fitted && !!style.emphasis;
      const italic = block.kind === "caption" && !!fonts.captionItalic;
      const measure = fitted ? font.measure : emphasisMeasure(font.measure, all);
      const layout = fitted
        ? scaleLayout(layoutSound(stripMarks(block.translation), box, font.measure, font.capRatio, sound ? SOUND_FILL : SIGN_FILL), style.scale)
        : style.fill_box
          ? layoutBox(block.translation, box, measure, { lineSpacing: style.line_spacing, scale: style.scale })
          : layoutText(block.translation, box, measure, {
            pitch: blockPitch(block.height, block.text, pitch),
            capRatio: font.capRatio,
            shape: "bubble",
            outline: block.bubble_polygon,
            scale: style.scale,
            lineSpacing: style.line_spacing,
            align: style.align,
          });
      const center = { x: layout.x + layout.width / 2, y: layout.y + layout.height / 2 };
      const words = style.align === "justify" ? justifyLines(layout, measure) : null;
      const runs = fitted ? null : lineRuns(layout, font.measure, style.align, words, all, italic);
      return { id: block.id, family: font.family, outline: sound, light: !!block.dark_background, words, layout, style, center, runs, italic };
    });
}

/** Naslov složen od slika slova originala (Faza 6a). */
function titleLettering(block: TextBlock, style: LetteringStyle): Lettering {
  const title = block.title!;
  const composed = composeTitle(block.translation, title, style);
  const opaque = style.opaque ?? !!title.hollow;
  const layout: Layout = {
    lines: [],
    placements: [],
    size: title.cap_height * composed.scale,
    lineHeight: 1,
    x: composed.x,
    y: composed.y,
    width: composed.width,
    height: composed.height,
    fits: composed.missing.length === 0,
  };
  return {
    id: block.id,
    family: "",
    outline: false,
    light: title.light,
    words: null,
    layout,
    style,
    // kos naslov se slaže u ispravljenom prostoru i vraća pod ugao oko iste tačke oko koje je ispravljen
    center: title.angle && title.center ? { x: title.center[0], y: title.center[1] } : { x: layout.x + layout.width / 2, y: layout.y + layout.height / 2 },
    tilt: title.angle ?? 0,
    skew: title.skew ?? 0,
    images: [
      // neprovidna slova: prvo ispune svih slova (papir pokriva crtež), pa konture preko njih
      ...(opaque ? composed.letters.filter((letter) => letter.fill).map((letter) => ({ ...letter, key: `${letter.key}f` })) : []),
      ...composed.letters,
    ].map((letter) => ({
      url: titleGlyphUrl(block.id, title, letter.key),
      x: letter.x,
      y: letter.y,
      width: letter.width,
      height: letter.height,
      rotation: letter.rotation,
    })),
  };
}

/** Uvećanje složenog reda oko njegovog centra (ručna veličina onomatopeje ili natpisa). */
function scaleLayout(layout: Layout, scale: number): Layout {
  if (scale === 1) return layout;
  const cx = layout.x + layout.width / 2;
  const cy = layout.y + layout.height / 2;
  const width = layout.width * scale;
  const height = layout.height * scale;
  return {
    ...layout,
    size: layout.size * scale,
    x: cx - width / 2,
    y: cy - height / 2,
    width,
    height,
    placements: layout.placements.map(() => ({ x: cx - width / 2, y: cy - height / 2, width })),
  };
}
