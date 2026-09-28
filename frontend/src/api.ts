export interface LlmModel {
  name: string;
  size: number | null;
  capabilities: string[];
  file?: string; // GGUF fajl koji llama-server drži
}

export interface Health {
  status: "ok" | "degraded";
  database: { ok: boolean; error?: string };
  worker: { ok: boolean; last_seen: string | null };
  llama_server: {
    ok: boolean;
    server?: "llama-server" | "ollama";
    url: string;
    model: string;
    version?: string;
    models?: LlmModel[];
    error?: string;
  };
}

export interface LlmResult {
  response: string;
  model: string;
  load_seconds: number;
  prompt_tokens_per_second: number;
  eval_tokens_per_second: number;
}

export type PageKind = "original" | "reference";

export interface Series {
  id: number;
  name: string;
  source_lang: string;
  target_lang: string;
  dialogue_font?: string | null;
  sfx_font?: string | null;
  caption_italic?: boolean; // naracija ukošena (kao u srpskim izdanjima)
  translation_notes?: string | null; // uputstvo za prevod serijala (likovi, uzrečice)
}

export interface FontInfo {
  key: string;
  name: string;
  kind: "dialogue" | "sfx" | "title";
  builtin: boolean;
  url: string;
}

export const DEFAULT_DIALOGUE_FONT = "comic-neue-bold";
export const DEFAULT_SFX_FONT = "bangers";

export interface Page {
  id: number;
  kind: PageKind;
  position: number;
  import_order: number;
  source_name: string;
  width: number;
  height: number;
  skip: boolean;
  ocr_reviewed: boolean;
  translation_reviewed: boolean;
  cleaned_at?: string | null;
  version?: string; // oznaka fajla slike: nova slika na istom broju stranice dobija novu adresu
}

export type BlockKind = "speech" | "thought" | "caption" | "sfx" | "other" | "title";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TextBlock extends Rect {
  id: number;
  page_id: number;
  position: number;
  kind: BlockKind;
  bubble_polygon: number[][] | null;
  ocr_text: string | null;
  text: string;
  confidence: number | null;
  ocr_model: string | null;
  source: string;
  needs_review: boolean;
  translation: string;
  translation_model: string | null;
  translation_status: TranslationStatus;
  translation_too_long: boolean;
  translation_note?: string | null; // napomena prevodioca (igra reči): samo za lekturu, ne ide u oblačić
  style?: LetteringStyle | null;
  angle?: number | null; // nagib originalne onomatopeje (stepeni)
  dark_background?: boolean | null; // tamna podloga posle čišćenja: prevod se slaže svetlim slovima
  title?: TitleGlyphs | null; // naslov: slova isečena iz originala i dopunjena (Faza 6a)
  continues_id?: number | null; // tekst se nastavlja u ovom bloku (kolone, prelomljen oblačić)
}

/** Jedno slovo naslova: slika sa providnošću i mere za slaganje (px slike). */
export interface TitleGlyph {
  key: string; // g0… slova originala, x0… dopunjena
  char: string;
  source: "original" | "fallback" | "accent" | "custom";
  width: number;
  height: number;
  baseline: number; // osnovna linija od vrha slike
  ink_left: number;
  ink_right: number;
  x?: number; // slova originala: položaj slike na stranici
  y?: number;
  row?: number;
  space_before?: boolean;
  gap_next?: number | null; // razmak do sledećeg slova originala
  parts?: GlyphPart[]; // sastavljeno slovo (6b): delovi, za ponovno uređivanje
  fill?: boolean; // ima ispunu (unutrašnjost šupljeg slova), slika {ključ}f
  font?: string; // napravljeno slovo: font od koga je
}

/**
 * Deo slova originala u sastavljenom slovu: izrez (poligon u pikselima izvornog slova) i
 * položaj njegove sredine na platnu novog slova, sa veličinom, ogledalom i rotacijom.
 */
export interface GlyphPart {
  source: string; // ključ izvornog slova
  polygon: number[][];
  x: number;
  y: number;
  scaleX: number; // negativno: ogledalo
  scaleY: number;
  rotation: number;
}

export interface TitleGlyphs {
  version: string;
  text: string; // tekst originala iz kog su slova isečena
  light: boolean;
  ink: number;
  background: number;
  left: number; // mastilo svih slova originala na stranici
  top: number;
  right: number;
  bottom: number;
  cap_height: number;
  max_scale: number; // koliko naslov sme da se uveća a da ne izađe iz trake
  gap: number;
  word_gap: number;
  found: number;
  expected: number;
  glyphs: TitleGlyph[];
  extra: TitleGlyph[];
  custom?: TitleGlyph[]; // sastavljena od delova (6b)
  font?: string; // font od koga su napravljena slova koja nedostaju (automatski izbor)
  fonts?: string[]; // fontovi koji se mogu izabrati za slovo koje nedostaje
  slant?: number; // nagib slova originala, stepeni
  hollow?: boolean; // slova originala su samo kontura
  paper?: number; // siva ispune (papir unutar šupljih slova)
  // kos naslov: slova su isečena ispravljena (ugao reda, kurziv), pa se složen prevod vraća pod
  // isti ugao i u isti kurziv oko `center`
  angle?: number; // stepeni, u smeru kazaljke (+ = red se spušta udesno)
  skew?: number; // nagib kurziva (tangens, gornji deo slova udesno)
  center?: [number, number] | null;
}

/** Ručne korekcije složenog prevoda (odstupanja od automatskog slaganja). */
export interface LetteringStyle {
  scale: number;
  dx: number;
  dy: number;
  rotation: number;
  align: "center" | "left" | "right" | "justify";
  line_spacing: number;
  font: string | null;
  fit: "fill" | "original"; // naslov: popuni širinu originala ili zadrži veličinu slova
  letter_spacing: number; // naslov: dodatni razmak slova, u visinama slova
  letters: Record<string, LetterStyle>; // naslov: izmene po rednom broju slova prevoda
  opaque?: boolean | null; // naslov: ispuna slova pokriva crtež; null = kao original (šuplja slova)
  // boja slova i obruba (naslovna, kolor strane); null = automatski: crno, a belo na tamnoj podlozi
  color?: string | null;
  outline_color?: string | null;
  outline_width?: number | null; // u veličinama slova; 0 = bez obruba
  fill_box?: boolean; // „Uklopi u okvir": tekst puni okvir bloka, veličina slova se bira slobodno
  emphasis?: boolean; // „Naglašeno": ceo blok podebljan i ukošen (vika, psovka), kao u srpskim izdanjima
  letter_fonts?: Record<string, string>; // naslov: font za slovo kojeg nema u originalu (K → Anton)
  cover?: boolean; // onomatopeja/natpis preko crteža: original se ne briše, nova slova ga prekriju obrubom
}

export interface LetterStyle {
  key?: string | null; // izabran primerak slova
  dx?: number; // pomeraj u visinama slova
  dy?: number;
  rotation?: number; // stepeni, oko sredine slova (naslov u luku)
}

export const AUTO_STYLE: LetteringStyle = {
  scale: 1,
  dx: 0,
  dy: 0,
  rotation: 0,
  align: "center",
  line_spacing: 1,
  font: null,
  fit: "fill",
  letter_spacing: 0,
  letters: {},
  opaque: null,
  color: null,
  outline_color: null,
  outline_width: null,
  fill_box: false,
  emphasis: false,
};

export type TranslationStatus = "none" | "draft" | "edited" | "approved";

export type BlockChanges = Partial<Rect> & {
  kind?: BlockKind;
  translation_note?: string | null;
  continues_id?: number | null;
  text?: string;
  needs_review?: boolean;
  translation?: string;
  translation_status?: TranslationStatus;
  style?: LetteringStyle | null;
};

export interface Job {
  id: number;
  type: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  project_id: number | null;
  progress: number;
  total: number;
  cancel_requested: boolean;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary {
  id: number;
  series: Series;
  issue_number: string | null;
  original_title: string | null;
  translated_title: string | null;
  created_at: string;
  page_count: number;
  reference_page_count: number;
  cover_page_id: number | null;
  cover_version?: string;
}

/** Stanje koraka obrade; preskočene stranice (naslovna, reklame) se ne broje. */
export interface ProjectProgress {
  pages: number;
  skipped: number[];
  with_blocks: number;
  /** automatski blokovi koje OCR nije pročitao (prekinuta obrada) */
  unread: number;
  blocks: number;
  translation: Partial<Record<TranslationStatus, number>>;
  proofread: number;
  cleaned: number;
  exported_at: string | null;
  /** izvoz u toku: crtanje u browseru ili pakovanje; stale = tab sa izvozom je verovatno zatvoren */
  export_active?: { stage: "drawing" | "packing"; done: number; total: number; stale: boolean } | null;
  ai_calls?: number; // AI prepravke natpisa (predlozi, i odbačeni)
  ai_cost?: number; // njihov zbirni trošak ($)
  changed_at: string | null; // izvoz stariji od ovoga je zastareo
}

export interface ProjectDetail extends ProjectSummary {
  pages: Page[];
  jobs: Job[];
  progress: ProjectProgress;
}

export interface NewProject {
  series_id: number;
  issue_number?: string;
  original_title?: string;
  translated_title?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail ?? `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const getHealth = () => request<Health>("/api/health");
export const runLlm = (prompt: string) => request<LlmResult>("/api/debug/llm", json("POST", { prompt }));

export const listSeries = () => request<Series[]>("/api/series");
export const updateSeries = (
  id: number,
  changes: { dialogue_font?: string | null; sfx_font?: string | null; caption_italic?: boolean; translation_notes?: string | null },
) =>
  request<Series>(`/api/series/${id}`, json("PATCH", changes));
export const listFonts = () => request<FontInfo[]>("/api/fonts");
export function uploadFont(file: File, kind: "dialogue" | "sfx") {
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file);
  return request<FontInfo>("/api/fonts", { method: "POST", body });
}
export const listProjects = () => request<ProjectSummary[]>("/api/projects");
export const getProject = (id: number) => request<ProjectDetail>(`/api/projects/${id}`);
export const createProject = (data: NewProject) =>
  request<ProjectDetail>("/api/projects", json("POST", data));
export const deleteProject = (id: number) =>
  request<void>(`/api/projects/${id}`, { method: "DELETE" });

export function importPages(projectId: number, kind: PageKind, files: File[]) {
  const form = new FormData();
  form.append("kind", kind);
  files.forEach((file) => form.append("files", file));
  return request<Job>(`/api/projects/${projectId}/imports`, { method: "POST", body: form });
}

export const deletePage = (id: number) => request<void>(`/api/pages/${id}`, { method: "DELETE" });
export const reorderPages = (projectId: number, kind: PageKind, pageIds: number[]) =>
  request<Page[]>(
    `/api/projects/${projectId}/pages/order`,
    json("PUT", { kind, page_ids: pageIds }),
  );

export const resetPageOrder = (projectId: number) =>
  request<Page[]>(`/api/projects/${projectId}/pages/reset-order`, { method: "POST" });

export const updatePage = (
  id: number,
  changes: { skip?: boolean; ocr_reviewed?: boolean; translation_reviewed?: boolean },
) =>
  request<Page>(`/api/pages/${id}`, json("PATCH", changes));

export const listBlocks = (pageId: number) => request<TextBlock[]>(`/api/pages/${pageId}/blocks`);
export const createBlock = (pageId: number, rect: Rect) =>
  request<TextBlock>(`/api/pages/${pageId}/blocks`, json("POST", rect));
export const updateBlock = (id: number, changes: BlockChanges) =>
  request<TextBlock>(`/api/blocks/${id}`, json("PATCH", changes));
export const deleteBlock = (id: number) => request<void>(`/api/blocks/${id}`, { method: "DELETE" });
export const cutTitle = (id: number) => request<TextBlock>(`/api/blocks/${id}/title`, { method: "POST" });
export function saveTitleGlyph(
  blockId: number,
  image: Blob,
  glyph: { char: string; baseline: number; parts: GlyphPart[]; key?: string },
  fill?: Blob,
): Promise<TextBlock> {
  const body = new FormData();
  body.append("file", image, "slovo.png");
  if (fill) body.append("fill", fill, "ispuna.png");
  body.append("char", glyph.char);
  body.append("baseline", String(glyph.baseline));
  body.append("parts", JSON.stringify(glyph.parts));
  if (glyph.key) body.append("key", glyph.key);
  return request<TextBlock>(`/api/blocks/${blockId}/glyphs`, { method: "POST", body });
}
export const deleteTitleGlyph = (blockId: number, key: string) =>
  request<TextBlock>(`/api/blocks/${blockId}/glyphs/${key}`, { method: "DELETE" });
export const titleGlyphUrl = (blockId: number, title: TitleGlyphs, key: string) =>
  `/api/blocks/${blockId}/glyphs/${key}.png?v=${title.version}`;
export const duplicateBlock = (id: number) =>
  request<TextBlock>(`/api/blocks/${id}/duplicate`, { method: "POST" });
export const reorderBlocks = (pageId: number, ids: number[]) =>
  request<TextBlock[]>(`/api/pages/${pageId}/blocks/order`, json("PUT", { block_ids: ids }));
export const mergeBlocks = (pageId: number, ids: number[]) =>
  request<TextBlock[]>(`/api/pages/${pageId}/blocks/merge`, json("POST", { block_ids: ids }));
export const autoOrderBlocks = (pageId: number) =>
  request<TextBlock[]>(`/api/pages/${pageId}/blocks/auto-order`, { method: "POST" });

export interface OcrModels {
  default_model: string;
  models: LlmModel[];
}

export const listOcrModels = () => request<OcrModels>("/api/ocr/models");
export const ocrBlock = (id: number, model?: string) =>
  request<TextBlock>(`/api/blocks/${id}/ocr`, json("POST", { model }));

export const getJob = (id: number) => request<Job>(`/api/jobs/${id}`);

/** AI prepravka natpisa: predlog u redu poslova; kvalitetno (flash) ili jeftino (flash-lite). */
export const requestAiPatch = (blockId: number, quality: "quality" | "cheap") =>
  request<Job>(`/api/blocks/${blockId}/ai-patch`, json("POST", { quality }));
export const aiImageUrl = (jobId: number) => `/api/jobs/${jobId}/ai-image`;
/** Već plaćeni predlozi za blok (najnoviji prvi): prihvataju se ponovo bez novog poziva modela. */
export interface AiProposal {
  job_id: number;
  model: string;
  cost: number | null;
  created_at: string;
}
export const listAiProposals = (blockId: number) => request<AiProposal[]>(`/api/blocks/${blockId}/ai-proposals`);
export const acceptAiPatch = (jobId: number) => request<Patch>(`/api/jobs/${jobId}/ai-accept`, { method: "POST" });
export const cancelJob = (id: number) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" });

/** Posao iz reda (čeka ili radi), sa nazivom projekta. */
export interface ActiveJob extends Job {
  project_title: string | null;
}

export const listActiveJobs = () => request<ActiveJob[]>("/api/jobs");
export const processPage = (pageId: number, model?: string) =>
  request<Job>(`/api/pages/${pageId}/process`, json("POST", { model }));
export const processProject = (projectId: number, model: string | undefined, replace: boolean) =>
  request<Job>(`/api/projects/${projectId}/process`, json("POST", { model, replace }));

export type GlossaryKind = "name" | "place" | "phrase";

export interface GlossaryEntry {
  id: number;
  series_id: number;
  source: string;
  target: string;
  kind: GlossaryKind;
  note: string | null;
  status: "suggested" | "approved";
  origin: string;
  occurrences: number;
}

export type GlossaryChanges = Partial<Pick<GlossaryEntry, "source" | "target" | "kind" | "note" | "status">>;

export const listGlossary = (seriesId: number) => request<GlossaryEntry[]>(`/api/series/${seriesId}/glossary`);
export const createGlossaryEntry = (seriesId: number, entry: { source: string; target: string; kind: GlossaryKind; note?: string }) =>
  request<GlossaryEntry>(`/api/series/${seriesId}/glossary`, json("POST", entry));
export const updateGlossaryEntry = (id: number, changes: GlossaryChanges) =>
  request<GlossaryEntry>(`/api/glossary/${id}`, json("PATCH", changes));
export const suggestGlossary = (seriesId: number, projectId: number, referenceProjectId: number) =>
  request<Job>(`/api/series/${seriesId}/glossary/suggest`, json("POST", { project_id: projectId, reference_project_id: referenceProjectId }));
export const deleteGlossaryEntry = (id: number) => request<void>(`/api/glossary/${id}`, { method: "DELETE" });

/** Glosar onomatopeja, zajednički za sve serijale; izvor su samo slova (WOAH! = WOAH). */
export interface SfxEntry {
  id: number;
  source: string;
  target: string;
  note: string | null;
}

/** Reč onomatopeje iz projekata koje nema u glosaru, sa predlogom po pravilu (SH i W). */
export interface SfxMissing {
  source: string;
  suggestion: string;
  count: number;
}

export type SfxChanges = Partial<Pick<SfxEntry, "source" | "target" | "note">>;

export const listSfx = () => request<SfxEntry[]>("/api/sfx-glossary");
export const listMissingSfx = () => request<SfxMissing[]>("/api/sfx-glossary/missing");
export const createSfx = (entry: { source: string; target: string; note?: string }) =>
  request<SfxEntry>("/api/sfx-glossary", json("POST", entry));
export const updateSfx = (id: number, changes: SfxChanges) => request<SfxEntry>(`/api/sfx-glossary/${id}`, json("PATCH", changes));
export const deleteSfx = (id: number) => request<void>(`/api/sfx-glossary/${id}`, { method: "DELETE" });
export const applySfx = (projectId: number) => request<{ changed: number }>(`/api/projects/${projectId}/sfx/apply`, json("POST", {}));

export const listTranslationModels = () => request<OcrModels>("/api/translation/models");
export const translateBlock = (id: number, model: string | undefined, shorter: boolean) =>
  request<TextBlock>(`/api/blocks/${id}/translate`, json("POST", { model, shorter }));
/** Uputstvo za model za slike (isto kao AI prepravka), za ručni rad u AI aplikaciji. */
export const getAiPrompt = (blockId: number) => request<{ prompt: string }>(`/api/blocks/${blockId}/ai-prompt`);

/** Probni prevod bloka sa izabranim stilom (bez njega aktivni); ništa se ne upisuje. */
export const previewTranslation = (id: number, styleId?: number) =>
  request<{ translation: string; note: string | null }>(`/api/blocks/${id}/translate/preview`, json("POST", { style_id: styleId }));

/** Sačuvan stil prevoda (Podešavanja); jedan je aktivan. Ugrađeni se ne briše, a može da se vrati na podrazumevani. */
export interface TranslationStyle {
  id: number;
  name: string;
  text: string;
  builtin: boolean;
  active: boolean;
  changed: boolean;
}

export const listStyles = () => request<TranslationStyle[]>("/api/translation-styles");
export const createStyle = (style: { name: string; text: string }) => request<TranslationStyle>("/api/translation-styles", json("POST", style));
export const updateStyle = (id: number, changes: { name?: string; text?: string }) =>
  request<TranslationStyle>(`/api/translation-styles/${id}`, json("PATCH", changes));
export const activateStyle = (id: number) => request<TranslationStyle>(`/api/translation-styles/${id}/activate`, { method: "POST" });
export const resetStyle = (id: number) => request<TranslationStyle>(`/api/translation-styles/${id}/reset`, { method: "POST" });
export const deleteStyle = (id: number) => request<void>(`/api/translation-styles/${id}`, { method: "DELETE" });

export const translatePage = (pageId: number, model?: string) =>
  request<Job>(`/api/pages/${pageId}/translate`, json("POST", { model }));
export const prepareProject = (projectId: number, ocrModel: string | undefined, translationModel: string | undefined) =>
  request<Job>(`/api/projects/${projectId}/prepare`, json("POST", { ocr_model: ocrModel, translation_model: translationModel }));
export const translateProject = (projectId: number, model: string | undefined, replace: boolean) =>
  request<Job>(`/api/projects/${projectId}/translate`, json("POST", { model, replace }));

export interface RatingCandidate {
  id: number;
  order: number;
  translation: string;
  score: number | null;
}

export interface RatingItem {
  item: number;
  page_position: number;
  block_position: number;
  source: string;
  candidates: RatingCandidate[];
}

export interface RatingStudy {
  study: string;
  total_items: number;
  rated_items: number;
  items: RatingItem[];
}

export interface RatingSummary {
  study: string;
  candidates: { candidate: string; average: number; good_share: number; count: number }[];
}

export const getRatingStudy = (study: string) => request<RatingStudy>(`/api/ratings/${study}`);
export const getRatingSummary = (study: string) => request<RatingSummary>(`/api/ratings/${study}/summary`);
export const rateTranslation = (study: string, id: number, score: number) =>
  request<RatingCandidate>(`/api/ratings/${study}/${id}`, json("PUT", { score }));

const versioned = (url: string, version?: string) => (version ? `${url}?v=${encodeURIComponent(version)}` : url);
export const pageImageUrl = (id: number, version?: string) => versioned(`/api/pages/${id}/image`, version);
// očišćena slika se menja pri svakom čišćenju, pa vreme čišćenja ide u URL (keš)
export const pageCleanUrl = (page: Page) => `/api/pages/${page.id}/clean-image?v=${encodeURIComponent(page.cleaned_at ?? "")}`;
export const pageThumbnailUrl = (id: number, version?: string) => versioned(`/api/pages/${id}/thumbnail`, version);

export function projectTitle(project: ProjectSummary): string {
  const issue = project.issue_number ? ` ${project.issue_number}` : "";
  const title = project.translated_title ?? project.original_title;
  return `${project.series.name}${issue}${title ? ` — ${title}` : ""}`;
}

export interface BlockReview {
  block_id: number;
  position: number;
  unknown: string[];
  glossary_missing: string[];
  /** hrvatske i ijekavske reči (TISUĆU, TKO, UVIJEK) */
  non_serbian?: string[];
  too_long: boolean;
  /** naglašene reči originala (`*…*`) nisu prenete u prevod */
  emphasis_missing?: boolean;
  /** onomatopeje [original, predlog] po pravilu (SH, W) ili produžene, koje čekaju potvrdu u glosaru */
  sfx_unconfirmed?: [string, string][];
  /** duga naracija bez kraja rečenice i bez veze sa nastavkom */
  maybe_continues?: boolean;
}

export interface PageReview {
  page_id: number;
  reviewed: boolean;
  blocks: BlockReview[];
}

export interface DictionaryWord {
  id: number;
  series_id: number;
  word: string;
}

export const getPageReview = (pageId: number) => request<PageReview>(`/api/pages/${pageId}/review`);
export const addDictionaryWord = (seriesId: number, word: string) =>
  request<DictionaryWord>(`/api/series/${seriesId}/dictionary`, json("POST", { word }));

export const cleanPage = (pageId: number) => request<Job>(`/api/pages/${pageId}/clean`, { method: "POST" });
export const cleanProject = (projectId: number) =>
  request<Job>(`/api/projects/${projectId}/clean`, { method: "POST" });

/** Ponovo izmeri oblike oblačića iz očišćenih strana (kad tekst „ne staje" u dovoljno velik oblačić). */
export const reshapeProject = (projectId: number) =>
  request<Job>(`/api/projects/${projectId}/shapes`, { method: "POST" });

export interface MaskStroke {
  // add: obriši bojom okoline, inpaint: preko crteža (LaMa), erase: vrati original;
  // patch-hide: obriši deo zakrpe (vidi se ono ispod), patch-show: vrati deo zakrpe
  mode: "add" | "erase" | "inpaint" | "patch-hide" | "patch-show";
  radius: number;
  points: [number, number][];
}

export const editMask = (pageId: number, strokes: MaskStroke[]) =>
  request<Page>(`/api/pages/${pageId}/mask`, json("POST", { strokes }));
/** Četkica po zakrpi: hide briše deo zakrpe, show ga vraća (original slike ostaje). */
export const editPatchMask = (patchId: number, strokes: { mode: "hide" | "show"; radius: number; points: [number, number][] }[]) =>
  request<Patch>(`/api/patches/${patchId}/mask`, json("POST", { strokes }));

/** Scenario za lektora: tabela oblačić po oblačić (HTML za čitanje, CSV za tabelu). */
export const projectScriptUrl = (projectId: number, format: "html" | "csv") =>
  `/api/projects/${projectId}/script?format=${format}`;

/** Zakrpa slikom preko stranice (Faza 6c): PNG doteran van aplikacije. */
export interface Patch {
  id: number;
  position: number;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  opacity: number;
  above_text: boolean;
  url: string;
}

export type PatchChanges = Partial<Omit<Patch, "id" | "url">>;

export const listPatches = (pageId: number) => request<Patch[]>(`/api/pages/${pageId}/patches`);
/** Zakrpa preko stranice; uz `matchPage` je siva na crno-beloj strani (AI aplikacije vraćaju boju). */
export function addPatch(pageId: number, file: File, box?: Rect, onBlock = false): Promise<Patch> {
  const body = new FormData();
  body.append("file", file, file.name);
  for (const [key, value] of Object.entries(box ?? {})) body.append(key, String(value));
  // zakrpa na bloku: u boji stranice i iznad teksta, da je natpis samog bloka ne pokrije
  if (onBlock) {
    body.append("match_page", "true");
    body.append("above_text", "true");
  }
  return request<Patch>(`/api/pages/${pageId}/patches`, { method: "POST", body });
}
export const updatePatch = (id: number, changes: PatchChanges) =>
  request<Patch>(`/api/patches/${id}`, json("PATCH", changes));
export const deletePatch = (id: number) => request<void>(`/api/patches/${id}`, { method: "DELETE" });
/** Isečak stranice u punoj rezoluciji (PNG) za doradu van aplikacije. */
export const pageCropUrl = (pageId: number, box: Rect, clean = true) =>
  `/api/pages/${pageId}/crop?x=${Math.round(box.x)}&y=${Math.round(box.y)}&width=${Math.round(box.width)}&height=${Math.round(box.height)}&clean=${clean}`;

/** Šta „Poništi" i „Ponovi" trenutno vraćaju; null znači da nema koraka. */
export interface PageHistory {
  undo: string | null;
  redo: string | null;
}

export interface HistoryStep extends PageHistory {
  action: string | null; // naziv radnje koja je poništena (ili ponovljena)
  blocks: TextBlock[];
}

export const pageHistory = (pageId: number) => request<PageHistory>(`/api/pages/${pageId}/history`);
export const undoPage = (pageId: number) =>
  request<HistoryStep>(`/api/pages/${pageId}/undo`, { method: "POST" });
export const redoPage = (pageId: number) =>
  request<HistoryStep>(`/api/pages/${pageId}/redo`, { method: "POST" });

export type ExportFormat = "cbz" | "pdf" | "zip";

export interface ExportSettings {
  format: ExportFormat;
  image_format: "jpeg" | "png";
  quality: number;
  skipped: "include" | "omit";
  first?: number | null;
  last?: number | null;
}

export interface Export extends ExportSettings {
  id: number;
  project_id: number;
  positions: number[];
  received: number[];
  status: "uploading" | "packing" | "done" | "failed";
  size: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  pages: { position: number; page_id: number; render: boolean }[];
}

export interface PageReadiness {
  position: number;
  page_id: number;
  skip: boolean;
  cleaned: boolean;
  reviewed: boolean;
  blocks: number;
  untranslated: number;
}

export const exportCheck = (projectId: number) => request<PageReadiness[]>(`/api/projects/${projectId}/export-check`);
export const listExports = (projectId: number) => request<Export[]>(`/api/projects/${projectId}/exports`);
export const createExport = (projectId: number, settings: ExportSettings) =>
  request<Export>(`/api/projects/${projectId}/exports`, json("POST", settings));
export const uploadExportPage = (exportId: number, position: number, image: Blob) =>
  request<Export>(`/api/exports/${exportId}/pages/${position}`, { method: "PUT", headers: { "Content-Type": "image/png" }, body: image });
export const finishExport = (exportId: number) => request<Job>(`/api/exports/${exportId}/finish`, { method: "POST" });
export const deleteExport = (exportId: number) => request<void>(`/api/exports/${exportId}`, { method: "DELETE" });
export const exportFileUrl = (exportId: number) => `/api/exports/${exportId}/file`;

