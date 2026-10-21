// Izvoz albuma iz browsera: svaka stranica se crta istim kodom kao u editoru i šalje backendu.

import { type Export, type FontInfo, type Page, type Series, type TextBlock, coveredBlocks, listBlocks, listPatches, pageCleanUrl, pageImageUrl, uploadExportPage } from "../api";
import { letterBlocks } from "../lettering/blocks";
import { loadFontMetrics, pageFonts } from "../lettering/fonts";
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
  const { dialogue, sound } = pageFonts(fonts, series, []);
  if (!dialogue || !sound) throw new Error("fontovi serijala nisu dostupni");
  const todo = exportJob.pages.filter((item) => item.render);
  const progress: ExportProgress = { done: 0, total: todo.length, overflow: [] };
  onProgress({ ...progress });
  for (const item of todo) {
    if (cancelled()) throw new Error("izvoz je prekinut");
    const page = pages.find((candidate) => candidate.id === item.page_id);
    if (!page) throw new Error(`stranica ${item.position} ne postoji`);
    const blocks: TextBlock[] = await listBlocks(page.id);
    const metrics = await loadFontMetrics(pageFonts(fonts, series, blocks).used);
    const patches = await listPatches(page.id);
    const lettering = letterBlocks(
      blocks,
      page.height,
      { dialogue: metrics[dialogue.key], sound: metrics[sound.key], byKey: (key) => metrics[key], captionItalic: !!series.caption_italic },
      coveredBlocks(patches),
    );
    if (lettering.some((entry) => !entry.layout.fits)) progress.overflow.push(page.position);
    const image = await renderPage({
      imageUrl: page.cleaned_at ? pageCleanUrl(page) : pageImageUrl(page.id, page.version),
      width: page.width,
      height: page.height,
      lettering,
      // zakrpe (ručne i AI prepravke) su deo stranice, isto kao u editoru i „Sačuvaj stranicu"
      patches,
      format: "png", // bez gubitaka; backend kodira jednom u izabrani format
    });
    await uploadExportPage(exportJob.id, item.position, image);
    progress.done += 1;
    onProgress({ ...progress, overflow: [...progress.overflow] });
  }
  return progress;
}
