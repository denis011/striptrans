// Učitavanje fontova u browser i merenje teksta na canvas-u (isti fontovi za prikaz i izvoz).

import { useEffect, useState } from "react";
import type { Measure } from "./layout";

export interface FontMetrics {
  family: string;
  measure: Measure;
  capRatio: number; // visina velikog slova / veličina slova
}

const SAMPLE_SIZE = 100;
const loads = new Map<string, Promise<void>>();

// porodica zavisi i od verzije fajla (?v=...), da ponovo dodat font ne dobije staru porodicu
export const familyName = (key: string, url = "") => {
  const version = /[?&]v=([\w-]+)/.exec(url)?.[1];
  return version ? `st-${key}-${version}` : `st-${key}`;
};

function loadFont(key: string, url: string): Promise<void> {
  let promise = loads.get(url);
  if (!promise) {
    promise =
      typeof FontFace === "undefined"
        ? Promise.resolve()
        : new FontFace(familyName(key, url), `url(${url})`).load().then((face) => {
            document.fonts.add(face);
          });
    loads.set(url, promise);
  }
  return promise;
}

function metrics(key: string, url: string): FontMetrics {
  const family = familyName(key, url);
  const context = document.createElement("canvas").getContext?.("2d") ?? null;
  if (!context) {
    // bez canvas-a (testovi): približno, kao da je font monospace
    return { family, measure: (text) => text.length * 0.6, capRatio: 0.7 };
  }
  context.font = `${SAMPLE_SIZE}px "${family}"`;
  const cache = new Map<string, number>();
  const measure: Measure = (text) => {
    let width = cache.get(text);
    if (width === undefined) {
      width = context.measureText(text).width / SAMPLE_SIZE;
      cache.set(text, width);
    }
    return width;
  };
  const capRatio = context.measureText("H").actualBoundingBoxAscent / SAMPLE_SIZE || 0.7;
  return { family, measure, capRatio };
}

/** Učitaj fontove (ključ → URL) i vrati njihova merenja. */
export async function loadFontMetrics(fonts: Record<string, string>): Promise<Record<string, FontMetrics>> {
  const entries = Object.entries(fonts);
  await Promise.all(entries.map(([key, url]) => loadFont(key, url).catch(() => undefined)));
  return Object.fromEntries(entries.map(([key, url]) => [key, metrics(key, url)]));
}

/** Učitaj fontove (ključ → URL) i vrati merenja kad su spremni. */
export function useFontMetrics(fonts: Record<string, string>): Record<string, FontMetrics> | null {
  const [ready, setReady] = useState<Record<string, FontMetrics> | null>(null);
  const signature = JSON.stringify(fonts);
  useEffect(() => {
    let cancelled = false;
    setReady(null);
    loadFontMetrics(JSON.parse(signature) as Record<string, string>).then((loaded) => {
      if (!cancelled) setReady(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [signature]);
  return ready;
}
