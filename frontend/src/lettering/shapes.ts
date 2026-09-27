// Opis složenog teksta kao Konva oblika: isti opis koriste editor (react-konva) i izvoz (Konva),
// pa je izvezena stranica tačno ono što se vidi u editoru.

import type { Lettering, PlacedRun } from "./blocks";
import { EMPHASIS_BOLD, EMPHASIS_SKEW, ITALIC_SKEW } from "./emphasis";

export interface GroupShape {
  x: number;
  y: number;
  offsetX: number;
  offsetY: number;
  rotation: number;
  skewX?: number; // kos naslov u kurzivu
}

export interface TextShape {
  x: number;
  y: number;
  width?: number; // bez širine: reč obostrano poravnatog reda, bez odsecanja
  text: string;
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  align: "left" | "center" | "right";
  wrap: "none";
  fill: string;
  stroke?: string;
  strokeWidth: number;
  fillAfterStrokeEnabled: boolean;
  lineJoin: "round";
  skewX?: number; // naglasak i ukošena naracija (negativno: slova nagnuta udesno)
  letterSpacing?: number; // naglasak: podebljana slova su šira
}

/** Slika slova naslova za Konva: rotira se oko svoje sredine. */
export interface ImageShape {
  url: string;
  x: number;
  y: number;
  width: number;
  height: number;
  offsetX: number;
  offsetY: number;
  rotation: number;
}

export const OVERFLOW_COLOR = "#b91c1c"; // tekst koji ne staje ni najmanjim slovima
const OUTLINE_WIDTH = 0.12; // beli obrub onomatopeje, u veličinama slova

/**
 * Grupa (pomeraj i rotacija oko sredine teksta) i po jedan tekst za svaki red (ili reč, kod
 * obostranog); naslov umesto teksta ima slike slova originala.
 */
export function letteringShapes(
  { layout, family, style, center, outline, light, words, images = [], tilt = 0, skew = 0, runs = null, italic = false }: Lettering,
  showOverflow = true,
): { group: GroupShape; texts: TextShape[]; images: ImageShape[] } {
  // boja iz stila bloka (naslovna, kolor strane); inače crno, a belo na tamnoj podlozi
  const ink = style.color ?? (light ? "#fff" : "#000");
  const edge = style.outline_color ?? (light ? "#000" : "#fff");
  // obrub: zadat u stilu, a inače samo onomatopeja (da se odvoji od crteža)
  const edgeWidth = style.outline_width ?? (outline || style.outline_color ? OUTLINE_WIDTH : 0);
  const common = {
    fontFamily: family,
    fontSize: layout.size,
    lineHeight: layout.lineHeight,
    wrap: "none" as const,
    fill: layout.fits || !showOverflow ? ink : OVERFLOW_COLOR,
    stroke: edgeWidth > 0 ? edge : undefined,
    strokeWidth: layout.size * edgeWidth,
    fillAfterStrokeEnabled: true,
    lineJoin: "round" as const,
  };
  // obostrano: poslednji red i red sa jednom reči se centriraju
  const align = style.align === "justify" ? "center" : style.align;
  const slant = (degrees: number) => Math.tan((degrees * Math.PI) / 180);
  /**
   * Deo reda: naglašen je podebljan (potez iste boje kao slova, uz širi razmak) i nagnut, a ukošena
   * naracija samo nagnuta. Konva naginje oko vrha reda, pa se deo pomera udesno da mu sredina slova
   * ostane na mestu. Uz obrub (onomatopeja, kolor strane) prvo ide obrub, pa podebljana slova preko.
   */
  const runShapes = (run: PlacedRun, y: number): TextShape[] => {
    const skew = run.emphasis ? slant(EMPHASIS_SKEW) : italic ? slant(ITALIC_SKEW) : 0;
    const base: TextShape = {
      ...common,
      x: run.x + (skew * layout.size * layout.lineHeight) / 2,
      y,
      text: run.text,
      align: "left",
      ...(skew ? { skewX: -skew } : {}),
    };
    if (!run.emphasis) return [base];
    const bold = EMPHASIS_BOLD * layout.size;
    const heavy = { ...base, letterSpacing: bold, stroke: base.fill, strokeWidth: bold, fillAfterStrokeEnabled: false };
    if (!common.stroke) return [heavy];
    return [{ ...base, letterSpacing: bold, strokeWidth: common.strokeWidth + bold }, heavy];
  };
  return {
    // kos naslov: ugao reda i kurziv originala se dodaju ručnoj rotaciji (oko sredine originala)
    group: {
      x: center.x + style.dx,
      y: center.y + style.dy,
      offsetX: center.x,
      offsetY: center.y,
      rotation: style.rotation + tilt,
      ...(skew ? { skewX: -skew } : {}),
    },
    images: images.map(({ url, x, y, width, height, rotation = 0 }) => ({
      url,
      x: x + width / 2,
      y: y + height / 2,
      width,
      height,
      offsetX: width / 2,
      offsetY: height / 2,
      rotation,
    })),
    texts: layout.lines.flatMap((line, index): TextShape[] => {
      const placement = layout.placements[index];
      const parts = runs?.[index];
      if (parts) return parts.flatMap((run) => runShapes(run, placement.y));
      const spread = words?.[index];
      if (spread) return spread.map((word) => ({ ...common, x: word.x, y: placement.y, text: word.text, align: "left" as const }));
      return [
        {
          ...common,
          // Konva odseca red širi od zadate širine, a njeno merenje se malo razlikuje od našeg: rezerva
          // od jedne veličine slova, raspoređena tako da poravnanje ostane isto
          x: placement.x - layout.size * { left: 0, center: 0.5, right: 1 }[align],
          y: placement.y,
          width: placement.width + layout.size,
          text: line,
          align,
        },
      ];
    }),
  };
}
