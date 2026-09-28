// Izvoz albuma iz browsera: svaka stranica se crta istim kodom kao u editoru i šalje backendu.

import { DEFAULT_DIALOGUE_FONT, DEFAULT_SFX_FONT, type Export, type FontInfo, type Page, type Series, type TextBlock, listBlocks, listPatches, pageCleanUrl, pageImageUrl, uploadExportPage } from "../api";
import { letterBlocks } from "../lettering/blocks";
import { loadFontMetrics } from "../lettering/fonts";
import { renderPage } from "./renderPage";

export interface ExportProgress {
  done: number;
  total: number;
  overflow: number[]; // stranice na kojima neki tekst ne staje
}

export interface ExportRun {
  exportJob: Export;
  pages: Page[];
  series: Series;
  fonts: FontInfo[];
  onProgress: (progress: ExportProgress) => void;
  cancelled: () => boolean;
}

/** Nacrtaj i pošalji sve stranice izvoza koje treba crtati (preskočene backend uzima same). */
export async function runExport({ exportJob, pages, series, fonts, onProgress, cancelled }: ExportRun): Promise<ExportProgress> {
  const pick = (key: string | null | undefined, fallback: string) => fonts.find((font) => font.key === key) ?? fonts.find((font) => font.key === fallback);
  const dialogue = pick(series.dialogue_font, DEFAULT_DIALOGUE_FONT);
  const sound = pick(series.sfx_font, DEFAULT_SFX_FONT);
  if (!dialogue || !sound) throw new Error("fontovi serijala nisu dostupni");
  const todo = exportJob.pages.filter((item) => item.render);
  const progress: ExportProgress = { done: 0, total: todo.length, overflow: [] };
  onProgress({ ...progress });
  for (const item of todo) {
    if (cancelled()) throw new Error("izvoz je prekinut");
    const page = pages.find((candidate) => candidate.id === item.page_id);
    if (!page) throw new Error(`stranica ${item.position} ne postoji`);
    const blocks: TextBlock[] = await listBlocks(page.id);
    const wanted = new Map([dialogue, sound].map((font) => [font.key, font.url]));
    for (const block of blocks) {
      const own = block.style?.font ? fonts.find((font) => font.key === block.style?.font) : undefined;
      if (own) wanted.set(own.key, own.url);
    }
    const metrics = await loadFontMetrics(Object.fromEntries(wanted));
    const lettering = letterBlocks(blocks, page.height, {
      dialogue: metrics[dialogue.key],
      sound: metrics[sound.key],
      byKey: (key) => metrics[key],
      captionItalic: !!series.caption_italic,
    });
    if (lettering.some((entry) => !entry.layout.fits)) progress.overflow.push(page.position);
    const image = await renderPage({
      imageUrl: page.cleaned_at ? pageCleanUrl(page) : pageImageUrl(page.id, page.version),
      width: page.width,
      height: page.height,
      lettering,
      // zakrpe (ručne i AI prepravke) su deo stranice, isto kao u editoru i „Sačuvaj stranicu"
      patches: await listPatches(page.id),
      format: "png", // bez gubitaka; backend kodira jednom u izabrani format
    });
    await uploadExportPage(exportJob.id, item.position, image);
    progress.done += 1;
    onProgress({ ...progress, overflow: [...progress.overflow] });
  }
  return progress;
}
