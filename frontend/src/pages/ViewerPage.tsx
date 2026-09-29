import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  type BlockChanges,
  type LetteringStyle,
  type MaskStroke,
  DEFAULT_DIALOGUE_FONT,
  DEFAULT_SFX_FONT,
  type Job,
  type Patch,
  type Rect,
  type TextBlock,
  addDictionaryWord,
  createSfx,
  listStyles,
  previewTranslation,
  addPatch,
  autoOrderBlocks,
  cancelJob,
  cleanPage,
  createBlock,
  cutTitle,
  deletePatch,
  deleteTitleGlyph,
  deleteBlock,
  editMask,
  editPatchMask,
  getAiPrompt,
  duplicateBlock,
  getJob,
  getPageReview,
  getProject,
  listBlocks,
  listFonts,
  listPatches,
  listOcrModels,
  listTranslationModels,
  mergeBlocks,
  ocrBlock,
  pageCleanUrl,
  pageImageUrl,
  pageCropUrl,
  pageHistory,
  pageThumbnailUrl,
  processPage,
  redoPage,
  projectTitle,
  reorderBlocks,
  saveTitleGlyph,
  translateBlock,
  translatePage,
  updateBlock,
  updatePage,
  undoPage,
  updatePatch,
  updateSeries,
  uploadFont,
} from "../api";
import { Ban, Boxes, Brush, CaseSensitive, Check, ChevronLeft, ChevronRight, Copy, ExternalLink, Download, Eraser, Eye, GalleryHorizontal, Image as ImageIcon, Languages, MousePointer2, PanelRight, Redo2, ScanText, Scissors, SquarePlus, Type, Undo2 } from "lucide-react";
import BlockPanel from "../components/BlockPanel";
import type { SavedGlyph } from "../components/GlyphEditor";
import Menu from "../components/Menu";
import ThemeToggle from "../components/ThemeToggle";
import { blockStyle, letterBlocks } from "../lettering/blocks";
import { useFontMetrics } from "../lettering/fonts";
import { type ImageFormat, downloadBlob, pageFilename, renderPage } from "../export/renderPage";
import JobStatus, { isActiveJob } from "../components/JobStatus";
import PageCanvas, { type Fit } from "../components/PageCanvas";
import { moveBlock, toggleSelection } from "../editor/blocks";
import { importRanks } from "../pageOrder";
import { loadSetting, saveSetting } from "../storage";
import { cropRect, fitInto, nudgeForKey, positionForKey } from "../viewer/navigation";
import { patchAt } from "../viewer/patchHit";
import type { FitMode } from "../viewer/zoom";

const FIT_BUTTONS: [FitMode, string, string][] = [
  ["page", "Cela stranica", "Cela"],
  ["width", "Širina", "Širina"],
  ["actual", "100 %", "1:1"],
];

type Mode = "select" | "draw" | "brush" | "text" | "patch";

/** Mere slike iz fajla (za uklapanje zakrpe bez izobličenja); null ako pregledač ne može da je pročita. */
async function imageSize(file: File): Promise<{ width: number; height: number } | null> {
  try {
    const bitmap = await createImageBitmap(file);
    const size = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return size;
  } catch {
    return null;
  }
}

const NUDGE_SAVE_DELAY = 400;
const AI_APP_URL = "https://gemini.google.com/app"; // AI aplikacija za ručni tok (pretplata korisnika)
const AI_TAB_KEY = "striptrans.aiTabOpened"; // Gemini je u ovoj sesiji već otvoren iz editora

function aiTabOpened(): boolean {
  try {
    return sessionStorage.getItem(AI_TAB_KEY) === "1";
  } catch {
    return false;
  }
}

function openAiApp() {
  window.open(AI_APP_URL, "_blank");
  try {
    sessionStorage.setItem(AI_TAB_KEY, "1");
  } catch {
    // bez sessionStorage-a Gemini se otvara pri svakoj pripremi
  }
} // ms bez strelice pre čuvanja pomeraja

const MODES = [
  { value: "select", label: "Izbor", short: "Izbor", Icon: MousePointer2 },
  { value: "draw", label: "Novi blok (N)", short: "Blok", Icon: SquarePlus },
  { value: "brush", label: "Četkica (B)", short: "Četkica", Icon: Brush },
  { value: "text", label: "Uredi tekst (T)", short: "Tekst", Icon: Type },
  { value: "patch", label: "Zakrpe (P)", short: "Zakrpe", Icon: ImageIcon },
] as const;

function isTyping(target: EventTarget | null): target is HTMLElement {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}

export default function ViewerPage() {
  const params = useParams();
  const projectId = Number(params.projectId);
  const position = Number(params.position);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fit, setFit] = useState<Fit>({ mode: "page", token: 0 });
  const [compare, setCompare] = useState(true);
  const [showBlocks, setShowBlocks] = useState(true);
  const [showClean, setShowClean] = useState(true);
  const [showLettering, setShowLettering] = useState(true);
  const [editLettering, setEditLettering] = useState(false);
  const [brush, setBrush] = useState<{ mode: MaskStroke["mode"]; radius: number } | null>(null);
  const [brushSettings, setBrushSettings] = useState<{ mode: MaskStroke["mode"]; radius: number }>({ mode: "add", radius: 12 });
  const [drawMode, setDrawMode] = useState(false);
  const [editPatches, setEditPatches] = useState(false);
  const [selectedPatchId, setSelectedPatchId] = useState<number | null>(null);
  // režim rada (Faza 7a): novi blok, četkica, uređivanje teksta i zakrpe isključuju jedan drugi
  const mode: Mode = drawMode ? "draw" : brush ? "brush" : editLettering ? "text" : editPatches ? "patch" : "select";
  const setMode = (next: Mode) => {
    setDrawMode(next === "draw");
    setBrush(next === "brush" ? brushSettings : null);
    setEditLettering(next === "text");
    setEditPatches(next === "patch");
    if (next !== "patch") setSelectedPatchId(null);
  };
  const toggleMode = (next: Mode) => setMode(mode === next ? "select" : next);
  const toggleModeFromKey = useEffectEvent(toggleMode);
  const [showPanel, setShowPanel] = useState<boolean>(() => loadSetting("striptrans.showPanel", true));
  const [showStrip, setShowStrip] = useState<boolean>(() => loadSetting("striptrans.showStrip", true));
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [ocrModel, setOcrModel] = useState<string | null>(() => loadSetting("striptrans.ocrModel", null));
  const [autoOcr, setAutoOcr] = useState<boolean>(() => loadSetting("striptrans.autoOcr", true));
  const [readingIds, setReadingIds] = useState<number[]>([]);
  const [pageJobId, setPageJobId] = useState<number | null>(null);
  const [translationModel, setTranslationModel] = useState<string | null>(() => loadSetting("striptrans.translationModel", null));
  const [translatingIds, setTranslatingIds] = useState<number[]>([]);
  const [onlyWarnings, setOnlyWarnings] = useState(false);
  const [note, setNote] = useState<string | null>(null);  // poruka posle „Poništi"/„Ponovi"

  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => getProject(projectId) });
  const pages = project.data?.pages ?? [];
  const originals = pages.filter((page) => page.kind === "original");
  const references = pages.filter((page) => page.kind === "reference");
  const count = originals.length;
  const page = originals.find((item) => item.position === position);
  const pageId = page?.id ?? 0;

  const pageJob = useQuery({
    queryKey: ["job", pageJobId],
    queryFn: () => getJob(pageJobId ?? 0),
    enabled: pageJobId !== null,
    refetchInterval: (query) => (isActiveJob(query.state.data) ? 1000 : false),
  });
  const processing = isActiveJob(pageJob.data);
  const blocksKey = ["blocks", pageId];
  const blocksQuery = useQuery({
    queryKey: blocksKey,
    queryFn: () => listBlocks(pageId),
    enabled: pageId > 0,
    // tokom obrade blokovi pristižu jedan po jedan
    refetchInterval: processing ? 2000 : false,
  });
  const blocks = blocksQuery.data ?? [];
  const historyKey = ["history", pageId];
  const setBlocks = (data: TextBlock[]) => queryClient.setQueryData(blocksKey, data);
  const refreshHistory = () => queryClient.invalidateQueries({ queryKey: historyKey });
  const refreshBlocks = () => {
    queryClient.invalidateQueries({ queryKey: blocksKey });
    refreshHistory();
  };
  const historyQuery = useQuery({ queryKey: historyKey, queryFn: () => pageHistory(pageId), enabled: pageId > 0 });
  const history = historyQuery.data ?? { undo: null, redo: null };
  const patchesKey = ["patches", pageId];
  const patchesQuery = useQuery({ queryKey: patchesKey, queryFn: () => listPatches(pageId), enabled: pageId > 0 });
  const patches = patchesQuery.data ?? [];
  const selectedPatch = patches.find((patch) => patch.id === selectedPatchId) ?? null;
  const refreshPatches = () => {
    queryClient.invalidateQueries({ queryKey: patchesKey });
    refreshHistory();
  };

  const reviewKey = ["review", pageId];
  const reviewQuery = useQuery({
    queryKey: reviewKey,
    queryFn: () => getPageReview(pageId),
    enabled: pageId > 0 && !processing,
  });
  const reviews = Object.fromEntries((reviewQuery.data?.blocks ?? []).map((item) => [item.block_id, item]));
  const warned = new Set(
    (reviewQuery.data?.blocks ?? [])
      .filter((item) => item.unknown.length > 0 || item.glossary_missing.length > 0 || (item.non_serbian?.length ?? 0) > 0 || item.too_long || item.emphasis_missing)
      .map((item) => item.block_id),
  );

  const fontsQuery = useQuery({ queryKey: ["fonts"], queryFn: listFonts, staleTime: 60_000 });
  const fontList = fontsQuery.data ?? [];
  const series = project.data?.series;
  const pickFont = (key: string | null | undefined, fallback: string) =>
    fontList.find((font) => font.key === key) ?? fontList.find((font) => font.key === fallback);
  const dialogueFont = pickFont(series?.dialogue_font, DEFAULT_DIALOGUE_FONT);
  const soundFont = pickFont(series?.sfx_font, DEFAULT_SFX_FONT);
  // fontovi serijala i fontovi zadati pojedinačnim blokovima
  const usedFonts = Object.fromEntries(
    fontList
      .filter((font) => font.key === dialogueFont?.key || font.key === soundFont?.key || blocks.some((block) => block.style?.font === font.key))
      .map((font) => [font.key, font.url]),
  );
  const fontMetrics = useFontMetrics(usedFonts);
  const pageLettering =
    page && dialogueFont && soundFont && fontMetrics?.[dialogueFont.key] && fontMetrics[soundFont.key]
      ? letterBlocks(blocks, page.height, {
          dialogue: fontMetrics[dialogueFont.key],
          sound: fontMetrics[soundFont.key],
          byKey: (key) => fontMetrics[key],
          captionItalic: !!series?.caption_italic,
        })
      : undefined;
  const lettering = showLettering ? pageLettering : undefined;
  // blokovi čiji tekst ne staje: panel kaže koji red je preširok i koliko
  const overflows = Object.fromEntries(
    (pageLettering ?? []).filter((item) => !item.layout.fits).map((item) => [item.id, item.layout.overflow ?? null]),
  );
  const [saveFormat, setSaveFormat] = useState<ImageFormat>("jpeg");
  const savePage = useMutation({
    mutationFn: async () => {
      if (!page || !pageLettering) throw new Error("fontovi se još učitavaju");
      const blob = await renderPage({
        imageUrl: page.cleaned_at ? pageCleanUrl(page) : pageImageUrl(page.id, page.version),
        width: page.width,
        height: page.height,
        lettering: pageLettering,
        patches,
        format: saveFormat,
      });
      downloadBlob(blob, pageFilename(project.data?.series.name ?? "strip", project.data?.issue_number ?? null, page.position, saveFormat));
    },
  });
  // isečak za doradu van aplikacije: izabran blok (sa malom marginom), inače cela stranica
  // (isti okvir, unutar stranice, dobija i zakrpa dodata dok je blok izabran)
  const cropSource = selectedIds.length === 1 ? blocks.find((block) => block.id === selectedIds[0]) : undefined;
  const cropBox = cropSource
    ? cropRect(cropSource, { width: page?.width ?? 0, height: page?.height ?? 0 })
    : { x: 0, y: 0, width: page?.width ?? 0, height: page?.height ?? 0 };
  const copyAiPrompt = async () => {
    if (!cropSource) return;
    try {
      const { prompt } = await getAiPrompt(cropSource.id);
      await navigator.clipboard.writeText(prompt);
      setNote("Uputstvo je kopirano: nalepi ga u AI aplikaciju (Ctrl+V), a sliku koju vrati kopiraj i nalepi ovde (Ctrl+V)");
    } catch (error) {
      setNote(`Uputstvo nije kopirano: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  // ručni AI tok bez fajlova: isečak originala ide u clipboard (Ctrl+V u AI aplikaciji), a slika koju
  // aplikacija vrati se lepi u editor (Ctrl+V) i postaje zakrpa na izabranom bloku
  const prepareForAi = async () => {
    if (!cropSource) return;
    const url = pageCropUrl(pageId, cropBox, false);
    try {
      // Promise<Blob> čuva dozvolu klika dok se isečak preuzima (Safari i Chrome)
      const png = fetch(url).then((response) => response.blob());
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      setNote(
        aiTabOpened()
          ? "Isečak je kopiran: pređi na Gemini tab (Ctrl+Tab), Ctrl+V, pa „Uputstvo za AI“ i još jednom Ctrl+V"
          : "Isečak je kopiran: u Gemini-ju Ctrl+V, pa „Uputstvo za AI“ i još jednom Ctrl+V",
      );
    } catch {
      // pregledač bez slike u clipboard-u: isečak se preuzima kao fajl
      const link = document.createElement("a");
      link.href = url;
      link.download = `isecak-blok-${cropSource.position}.png`;
      link.click();
      setNote("Isečak je preuzet kao fajl (pregledač ne dozvoljava sliku u clipboard-u)");
    }
    // Gemini prekida vezu sa tabom koji ga otvori (Cross-Origin-Opener-Policy), pa ga aplikacija ne može
    // pronaći ni prebaciti u prvi plan: otvara se samo prvi put u sesiji, dalje ga korisnik bira sam
    if (!aiTabOpened()) openAiApp();
  };
  const changeStyle = (id: number, changes: Partial<LetteringStyle> | null) => {
    const block = blocks.find((item) => item.id === id);
    if (!block) return;
    changeBlock(id, { style: changes === null ? null : { ...blockStyle(block), ...changes } });
  };
  const addFont = useMutation({
    mutationFn: (file: File) => uploadFont(file, "dialogue"),
    onSuccess: (font) => {
      queryClient.invalidateQueries({ queryKey: ["fonts"] });
      seriesFonts.mutate({ dialogue_font: font.key });
    },
  });
  const seriesFonts = useMutation({
    mutationFn: (changes: { dialogue_font?: string; sfx_font?: string; caption_italic?: boolean }) => updateSeries(series?.id ?? 0, changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });

  const ocrModels = useQuery({ queryKey: ["ocr-models"], queryFn: listOcrModels, staleTime: 60_000 });
  const modelNames = ocrModels.data?.models.map((model) => model.name) ?? [];
  const activeModel = [ocrModel, ocrModels.data?.default_model, modelNames[0]].find(
    (name): name is string => !!name && modelNames.includes(name),
  );
  const read = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) {
        setReadingIds((current) => [...current, id]);
        try {
          const block = await ocrBlock(id, activeModel);
          queryClient.setQueryData<TextBlock[]>(["blocks", block.page_id], (old) =>
            old?.map((item) => (item.id === block.id ? block : item)),
          );
        } finally {
          setReadingIds((current) => current.filter((item) => item !== id));
        }
      }
    },
  });
  const readBlocks = read.mutate;
  const translationModels = useQuery({ queryKey: ["translation-models"], queryFn: listTranslationModels, staleTime: 60_000 });
  const translationNames = translationModels.data?.models.map((model) => model.name) ?? [];
  const activeTranslationModel = [translationModel, translationModels.data?.default_model, translationNames[0]].find(
    (name): name is string => !!name && translationNames.includes(name),
  );
  const translate = useMutation({
    mutationFn: async ({ id, shorter }: { id: number; shorter: boolean }) => {
      setTranslatingIds((current) => [...current, id]);
      try {
        const block = await translateBlock(id, activeTranslationModel, shorter);
        queryClient.setQueryData<TextBlock[]>(["blocks", block.page_id], (old) =>
          old?.map((item) => (item.id === block.id ? block : item)),
        );
      } finally {
        setTranslatingIds((current) => current.filter((item) => item !== id));
      }
    },
  });

  const create = useMutation({
    mutationFn: (rect: Rect) => createBlock(pageId, rect),
    onSuccess: (block) => {
      refreshBlocks();
      setSelectedIds([block.id]);
      setDrawMode(false);
      if (autoOcr) readBlocks([block.id]);
    },
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: BlockChanges }) => updateBlock(id, changes),
    onMutate: ({ id, changes }) =>
      queryClient.setQueryData<TextBlock[]>(blocksKey, (old) =>
        old?.map((block) => (block.id === id ? { ...block, ...changes } : block)),
      ),
    onSettled: () => {
      refreshBlocks();
      queryClient.invalidateQueries({ queryKey: reviewKey });
    },
  });
  const historyStep = useMutation({
    mutationFn: (kind: "undo" | "redo") => (kind === "undo" ? undoPage(pageId) : redoPage(pageId)),
    onSuccess: (step, kind) => {
      setBlocks(step.blocks);
      queryClient.setQueryData(historyKey, { undo: step.undo, redo: step.redo });
      setSelectedIds((ids) => ids.filter((id) => step.blocks.some((block) => block.id === id)));
      queryClient.invalidateQueries({ queryKey: reviewKey });
      queryClient.invalidateQueries({ queryKey: patchesKey });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });  // očišćena slika posle četkice
      if (step.action && kind === "undo") setNote(`Poništeno: ${step.action}`);
      if (step.action && kind === "redo") setNote(`Ponovljeno: ${step.action}`);
    },
  });
  const stepHistory = useEffectEvent((kind: "undo" | "redo") => historyStep.mutate(kind));
  const deletePatchFromKey = useEffectEvent((id: number) => removePatch.mutate(id));
  const newPatch = useMutation({
    // sa izabranim blokom zakrpa pada tačno na mesto izvezenog isečka, u boji stranice
    mutationFn: async (file: File) => {
      if (!cropSource) return addPatch(pageId, file);
      const size = await imageSize(file);
      return addPatch(pageId, file, size ? fitInto(cropBox, size) : cropBox, true);
    },
    onSuccess: (patch) => {
      queryClient.setQueryData<Patch[]>(patchesKey, (old) => [...(old ?? []), patch]);
      refreshHistory();
      setMode("patch");
      setSelectedPatchId(patch.id);
    },
  });
  const changePatchMutation = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: Parameters<typeof updatePatch>[1] }) => updatePatch(id, changes),
    onMutate: ({ id, changes }) =>
      queryClient.setQueryData<Patch[]>(patchesKey, (old) =>
        old?.map((patch) => (patch.id === id ? { ...patch, ...changes } : patch)),
      ),
    onSettled: () => refreshPatches(),
  });
  const removePatch = useMutation({
    mutationFn: deletePatch,
    onSuccess: () => {
      setSelectedPatchId(null);
      refreshPatches();
    },
  });
  const changePatch = changePatchMutation.mutate;
  const cutTitleMutation = useMutation({ mutationFn: cutTitle, onSettled: () => refreshBlocks() });
  const saveGlyph = useMutation({
    mutationFn: ({ id, image, glyph, fill }: { id: number; image: Blob; glyph: SavedGlyph; fill?: Blob }) => saveTitleGlyph(id, image, glyph, fill),
    onSettled: () => refreshBlocks(),
  });
  const deleteGlyph = useMutation({
    mutationFn: ({ id, key }: { id: number; key: string }) => deleteTitleGlyph(id, key),
    onSettled: () => refreshBlocks(),
  });
  const remove = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) await deleteBlock(id);
    },
    onSuccess: () => {
      setSelectedIds([]);
      refreshBlocks();
    },
  });
  const reorder = useMutation({
    mutationFn: (ids: number[]) => reorderBlocks(pageId, ids),
    onSuccess: (data) => {
      setBlocks(data);
      refreshHistory();
    },
  });
  const merge = useMutation({
    mutationFn: (ids: number[]) => mergeBlocks(pageId, ids),
    onSuccess: (data) => {
      setBlocks(data);
      setSelectedIds(data.filter((block) => selectedIds.includes(block.id)).map((block) => block.id));
      refreshHistory();
    },
  });
  const duplicate = useMutation({
    mutationFn: duplicateBlock,
    onSuccess: (block) => {
      refreshBlocks();
      setSelectedIds([block.id]);
    },
  });
  const autoOrder = useMutation({
    mutationFn: () => autoOrderBlocks(pageId),
    onSuccess: (data) => {
      setBlocks(data);
      refreshHistory();
    },
  });
  const addWord = useMutation({
    mutationFn: (word: string) => addDictionaryWord(project.data?.series.id ?? 0, word),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["review"] }),
  });
  const translationStyles = useQuery({ queryKey: ["translation-styles"], queryFn: listStyles });
  const confirmSfx = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) => createSfx({ source, target }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review"] });
      queryClient.invalidateQueries({ queryKey: ["sfx-glossary"] });
    },
  });
  const flags = useMutation({
    mutationFn: (changes: { skip?: boolean; ocr_reviewed?: boolean; translation_reviewed?: boolean }) => updatePage(pageId, changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const translatePageMutation = useMutation({
    mutationFn: () => translatePage(pageId, activeTranslationModel),
    onSuccess: (job: Job) => setPageJobId(job.id),
  });
  const maskMutation = useMutation({
    mutationFn: (stroke: MaskStroke) => editMask(pageId, [stroke]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      refreshBlocks(); // oblik oblačića se meri ponovo
    },
  });
  // četkica po zakrpi: izabrana zakrpa, inače najgornja na mestu gde potez počinje
  const patchMaskMutation = useMutation({
    mutationFn: (stroke: MaskStroke) => {
      const [x, y] = stroke.points[0];
      const target = selectedPatch ?? patchAt(patches, x, y);
      if (!target) throw new Error("Potez nije počeo na zakrpi.");
      const mode = stroke.mode === "patch-hide" ? "hide" : "show";
      return editPatchMask(target.id, [{ mode, radius: stroke.radius, points: stroke.points }]);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: patchesKey }),
  });
  const cleanMutation = useMutation({
    mutationFn: () => cleanPage(pageId),
    onSuccess: (job: Job) => setPageJobId(job.id),
  });
  const processMutation = useMutation({
    mutationFn: () => processPage(pageId, activeModel),
    onSuccess: (job: Job) => setPageJobId(job.id),
  });
  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: (job) => queryClient.setQueryData(["job", job.id], job),
  });
  const removeBlocks = remove.mutate;
  const markReviewed = flags.mutate;
  const mutationError = [create, update, remove, reorder, merge, duplicate, autoOrder, flags, read, processMutation, cleanMutation, maskMutation, savePage, cancelMutation, translate, translatePageMutation, cutTitleMutation, deleteGlyph].find((m) => m.error)?.error;

  useEffect(() => {
    setSelectedIds([]);
    setDrawMode(false);
    setPageJobId(null);
  }, [pageId]);

  const pageJobStatus = pageJob.data?.status;
  useEffect(() => {
    if (pageJobStatus && pageJobStatus !== "queued" && pageJobStatus !== "running") {
      queryClient.invalidateQueries({ queryKey: ["blocks"] });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    }
  }, [pageJobStatus, projectId, queryClient]);

  const approveAndAdvance = useEffectEvent((wholePage: boolean) => {
    const pending = blocks.filter((block) => block.translation && block.translation_status !== "approved");
    if (wholePage) {
      // Ctrl+Shift+Enter: odobri sve prevode, obeleži stranicu i pređi na sledeću
      for (const block of pending) changeBlock(block.id, { translation_status: "approved" });
      markReviewed({ translation_reviewed: true });
      if (position < count) navigate(`/projects/${projectId}/pages/${position + 1}`);
      return;
    }
    const current = blocks.find((block) => selectedIds.includes(block.id)) ?? pending[0];
    if (!current?.translation) return;
    changeBlock(current.id, { translation_status: "approved" });
    const next = pending.find((block) => block.position > current.position);
    setSelectedIds(next ? [next.id] : []);
  });

  // strelice pomeraju izabranu zakrpu ili blokove: odmah na ekranu, a na server (i u istoriju)
  // jednom, kad se strelice puste na trenutak ili kad se pređe na drugu stranicu
  const nudgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nudged = useRef<{ patches: Map<number, Rect>; blocks: Map<number, Rect> }>({ patches: new Map(), blocks: new Map() });
  const saveNudge = useEffectEvent(() => {
    if (nudgeTimer.current) clearTimeout(nudgeTimer.current);
    nudgeTimer.current = null;
    const { patches: movedPatches, blocks: movedBlocks } = nudged.current;
    nudged.current = { patches: new Map(), blocks: new Map() };
    for (const [id, { x, y }] of movedPatches) changePatch({ id, changes: { x, y } });
    for (const [id, { x, y }] of movedBlocks) changeBlock(id, { x, y });
  });
  const nudge = useEffectEvent((dx: number, dy: number): boolean => {
    if (editPatches && selectedPatchId) {
      const moved = queryClient
        .setQueryData<Patch[]>(patchesKey, (old) =>
          old?.map((item) => (item.id === selectedPatchId ? { ...item, x: item.x + dx, y: item.y + dy } : item)),
        )
        ?.find((item) => item.id === selectedPatchId);
      if (moved) nudged.current.patches.set(moved.id, moved);
    } else if (selectedIds.length > 0 && !editPatches && !drawMode && !brush) {
      const limit = { width: page?.width ?? Infinity, height: page?.height ?? Infinity };
      const updated = queryClient.setQueryData<TextBlock[]>(blocksKey, (old) =>
        old?.map((block) =>
          selectedIds.includes(block.id)
            ? {
                ...block,
                x: Math.min(Math.max(0, block.x + dx), Math.max(0, limit.width - block.width)),
                y: Math.min(Math.max(0, block.y + dy), Math.max(0, limit.height - block.height)),
              }
            : block,
        ),
      );
      for (const block of updated ?? []) if (selectedIds.includes(block.id)) nudged.current.blocks.set(block.id, block);
    } else {
      return false;
    }
    if (nudgeTimer.current) clearTimeout(nudgeTimer.current);
    nudgeTimer.current = setTimeout(saveNudge, NUDGE_SAVE_DELAY);
    return true;
  });
  useEffect(() => () => saveNudge(), [pageId]);

  // slika nalepljena u editor (Ctrl+V) postaje zakrpa: na izabranom bloku ide na njegovo mesto
  const pasteImage = useEffectEvent((event: ClipboardEvent) => {
    if (isTyping(event.target)) return;
    const file = [...(event.clipboardData?.files ?? [])].find((item) => item.type.startsWith("image/"));
    if (!file) return;
    event.preventDefault();
    newPatch.mutate(file);
  });
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => pasteImage(event);
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target)) {
        if (event.key === "Escape") event.target.blur();
        return;
      }
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        approveAndAdvance(event.shiftKey);
        return;
      }
      if (event.key === "Escape") {
        if (drawMode || brush || editLettering || selectedIds.length > 0) {
          toggleModeFromKey("select");
          setSelectedIds([]);
        } else {
          navigate(`/projects/${projectId}`);
        }
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (editPatches && selectedPatchId) {
          event.preventDefault();
          deletePatchFromKey(selectedPatchId);
          return;
        }
        if (selectedIds.length > 0) {
          event.preventDefault();
          removeBlocks(selectedIds);
          return;
        }
      }
      if (event.key.toLowerCase() === "z" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        stepHistory(event.shiftKey ? "redo" : "undo");
        return;
      }
      if (event.key.toLowerCase() === "y" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        stepHistory("redo");
        return;
      }
      if (event.key.toLowerCase() === "n" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        toggleModeFromKey("draw");
        return;
      }
      if (event.key.toLowerCase() === "b" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        toggleModeFromKey("brush");
        return;
      }
      if (event.key.toLowerCase() === "t" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        toggleModeFromKey("text");
        return;
      }
      if (event.key.toLowerCase() === "p" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        toggleModeFromKey("patch");
        return;
      }
      if (event.key.toLowerCase() === "r" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (selectedIds.length > 0) readBlocks(selectedIds);
        return;
      }
      const delta = event.ctrlKey || event.metaKey || event.altKey ? null : nudgeForKey(event.key, event.shiftKey);
      if (delta && nudge(delta[0], delta[1])) {
        event.preventDefault();
        return;
      }
      const next = positionForKey(event.key, position, count);
      if (next === null) return;
      event.preventDefault();
      navigate(`/projects/${projectId}/pages/${next}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [position, count, projectId, navigate, drawMode, brush, editLettering, editPatches, selectedIds, selectedPatchId, removeBlocks, readBlocks]);

  useEffect(() => {
    if (!note) return;
    const timer = window.setTimeout(() => setNote(null), 4000);
    return () => window.clearTimeout(timer);
  }, [note]);

  useEffect(() => {
    // susedne stranice se učitavaju unapred da prelazak bude bez čekanja
    for (const item of project.data?.pages ?? []) {
      if (Math.abs(item.position - position) === 1) new Image().src = pageImageUrl(item.id, item.version);
    }
    document.querySelector(".filmstrip .current")?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [position, project.data]);

  if (project.isPending) return <main className="container">Učitavanje…</main>;
  if (project.isError) {
    return (
      <main className="container">
        <p className="error">{project.error.message}</p>
      </main>
    );
  }
  if (!page) {
    return (
      <main className="container">
        <p>
          Stranica {position} ne postoji. <Link to={`/projects/${projectId}`}>Nazad na projekat</Link>
        </p>
      </main>
    );
  }

  const reference = references.find((item) => item.position === position);
  const showReference = compare && references.length > 0;
  const importRank = importRanks(originals).get(page.id);
  const go = (target: number) => navigate(`/projects/${projectId}/pages/${target}`);
  const select = (id: number | null, additive: boolean) =>
    setSelectedIds((current) => (id === null ? [] : toggleSelection(current, id, additive)));
  const changeBlock = (id: number, changes: BlockChanges) => update.mutate({ id, changes });

  return (
    <div className="viewer">
      <header className="editor-header">
        <Link to="/" className="brand">
          StripTrans
        </Link>
        <span className="divider" />
        <Link to={`/projects/${projectId}`} className="project-link" title="Nazad na projekat (Esc)">
          ← {projectTitle(project.data)}
        </Link>
        <div className="page-nav">
          <button type="button" className="icon-button" onClick={() => go(position - 1)} disabled={position <= 1} aria-label="Prethodna stranica" title="Prethodna stranica (←)">
            <ChevronLeft size={18} aria-hidden />
          </button>
          <span data-testid="page-indicator">
            {position} / {count}
          </span>
          <button type="button" className="icon-button" onClick={() => go(position + 1)} disabled={position >= count} aria-label="Sledeća stranica" title="Sledeća stranica (→)">
            <ChevronRight size={18} aria-hidden />
          </button>
          {importRank !== position && <span className="moved-from">(izvorno {importRank})</span>}
        </div>
        <div className="segmented">
          {FIT_BUTTONS.map(([fitMode, label, short]) => (
            <button
              key={fitMode}
              type="button"
              aria-label={label}
              title={label}
              className={fit.mode === fitMode ? "active" : ""}
              onClick={() => setFit((current) => ({ mode: fitMode, token: current.token + 1 }))}
            >
              {short}
            </button>
          ))}
        </div>
        <span className="spacer" />
        <label className={`chip${page.ocr_reviewed ? " on" : ""}`} title="Tekst originala (OCR) na stranici je proveren">
          <input type="checkbox" aria-label="Stranica pregledana" checked={page.ocr_reviewed} onChange={(event) => flags.mutate({ ocr_reviewed: event.target.checked })} />
          {page.ocr_reviewed && <Check size={14} aria-hidden />} OCR proveren
        </label>
        <label className={`chip${page.translation_reviewed ? " on" : ""}`} title="Prevod na stranici je lektorisan (Ctrl+Shift+Enter)">
          <input type="checkbox" aria-label="Stranica lektorisana" checked={page.translation_reviewed} onChange={(event) => flags.mutate({ translation_reviewed: event.target.checked })} />
          {page.translation_reviewed && <Check size={14} aria-hidden />} Lektorisana
        </label>
        <label className={`chip skip${page.skip ? " on" : ""}`} title="Stranica se ne obrađuje (naslovna, reklama) i ulazi u album neizmenjena">
          <input type="checkbox" aria-label="Preskoči stranicu" checked={page.skip} onChange={(event) => flags.mutate({ skip: event.target.checked })} />
          {page.skip && <Ban size={14} aria-hidden />} Preskoči
        </label>
        <span className="divider" />
        <button
          type="button"
          className="icon-button"
          aria-pressed={showStrip}
          aria-label="Sličice stranica"
          title="Sličice stranica na dnu"
          onClick={() => {
            setShowStrip(!showStrip);
            saveSetting("striptrans.showStrip", !showStrip);
          }}
        >
          <GalleryHorizontal size={18} aria-hidden />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-pressed={showPanel}
          aria-label="Panel blokova"
          title="Panel blokova desno"
          onClick={() => {
            setShowPanel(!showPanel);
            saveSetting("striptrans.showPanel", !showPanel);
          }}
        >
          <PanelRight size={18} aria-hidden />
        </button>
        <ThemeToggle />
      </header>
      <div className="tools">
        <div className="segmented" role="group" aria-label="Režim rada">
          {MODES.map(({ value, label, short, Icon }) => (
            <button
              key={value}
              type="button"
              aria-label={label}
              aria-pressed={mode === value}
              title={label}
              className={mode === value ? "active" : ""}
              disabled={value === "text" && !showLettering}
              onClick={() => (value === "select" ? setMode("select") : toggleMode(value))}
            >
              <Icon size={16} aria-hidden />
              {short}
            </button>
          ))}
        </div>
        <div className="toolbar-group">
          <button
            type="button"
            className="icon-button"
            aria-label="Poništi"
            title={history.undo ? `Poništi: ${history.undo} (Ctrl+Z)` : "Nema šta da se poništi"}
            disabled={!history.undo || historyStep.isPending}
            onClick={() => historyStep.mutate("undo")}
          >
            <Undo2 size={16} aria-hidden />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Ponovi"
            title={history.redo ? `Ponovi: ${history.redo} (Ctrl+Shift+Z)` : "Nema šta da se ponovi"}
            disabled={!history.redo || historyStep.isPending}
            onClick={() => historyStep.mutate("redo")}
          >
            <Redo2 size={16} aria-hidden />
          </button>
        </div>
        {note && <span className="note">{note}</span>}
        {editLettering && !note && (
          <span className="note">Dvoklik na tekst: izmena na slici (Ctrl+Enter čuva, Esc odustaje)</span>
        )}
        {brush && (
          <div className="mode-tools">
            <select
              aria-label="Mod četkice"
              value={brush.mode}
              onChange={(event) => {
                const next = { ...brush, mode: event.target.value as MaskStroke["mode"] };
                setBrush(next);
                setBrushSettings(next);
              }}
            >
              <option value="add">obriši tekst (belo)</option>
              <option value="inpaint">obriši preko crteža</option>
              <option value="erase">vrati original</option>
              <option value="patch-hide">obriši zakrpu</option>
              <option value="patch-show">vrati zakrpu</option>
            </select>
            <input
              type="range"
              aria-label="Veličina četkice"
              title={`Veličina četkice: ${brush.radius} px`}
              min={3}
              max={60}
              value={brush.radius}
              onChange={(event) => {
                const next = { ...brush, radius: Number(event.target.value) };
                setBrush(next);
                setBrushSettings(next);
              }}
            />
            {patchMaskMutation.isError && <span className="error">{patchMaskMutation.error.message}</span>}
          </div>
        )}
        {editPatches && (
          <div className="mode-tools">
            <label
              className="button"
              title={
                cropSource
                  ? `Slika ide na mesto isečka bloka ${cropSource.position}, bez izobličenja i iznad teksta (siva na crno-beloj strani)`
                  : "Slika (PNG sa providnošću) preko stranice; izaberi blok da padne na njegovo mesto"
              }
            >
              <ImageIcon size={16} aria-hidden /> {cropSource ? `Zakrpa na blok ${cropSource.position}…` : "Dodaj zakrpu…"}
              <input
                type="file"
                accept="image/png,image/webp,image/jpeg"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) newPatch.mutate(file);
                  event.target.value = "";
                }}
              />
            </label>
            <a
              className="button"
              title="Isečak izabranog bloka (ili cele stranice) u punoj rezoluciji, za doradu van aplikacije"
              href={pageCropUrl(pageId, cropBox, !!page.cleaned_at)}
              download
            >
              <Scissors size={16} aria-hidden /> Izvezi isečak
            </a>
            {cropSource && (
              <>
              <button
                type="button"
                title="Kopira isečak originala (sa italijanskim natpisom); prvi put otvara i Gemini. Tamo Ctrl+V, pa „Uputstvo za AI“"
                onClick={prepareForAi}
              >
                <Scissors size={16} aria-hidden /> Pripremi za AI
              </button>
              <button type="button" className="icon-button" aria-label="Otvori Gemini" title="Otvori Gemini u novom tabu (ako si ga zatvorio)" onClick={openAiApp}>
                <ExternalLink size={16} aria-hidden />
              </button>
              </>
            )}
            {cropSource && (
              <button
                type="button"
                aria-label="Kopiraj uputstvo za AI"
                disabled={!cropSource.translation}
                title={cropSource.translation ? "Uputstvo za AI aplikaciju (pretplata): zameni natpis prevodom istim slovima" : "Blok nema prevod"}
                onClick={copyAiPrompt}
              >
                <Copy size={16} aria-hidden /> Uputstvo za AI
              </button>
            )}
            {selectedPatch && (
              <>
                <input
                  type="range"
                  aria-label="Providnost zakrpe"
                  title={`Providnost: ${Math.round(selectedPatch.opacity * 100)} %`}
                  min={10}
                  max={100}
                  value={Math.round(selectedPatch.opacity * 100)}
                  onChange={(event) => changePatch({ id: selectedPatch.id, changes: { opacity: Number(event.target.value) / 100 } })}
                />
                <label title="Zakrpa se crta i preko složenog prevoda">
                  <input
                    type="checkbox"
                    checked={selectedPatch.above_text}
                    onChange={(event) => changePatch({ id: selectedPatch.id, changes: { above_text: event.target.checked } })}
                  />
                  Iznad teksta
                </label>
                <button type="button" onClick={() => removePatch.mutate(selectedPatch.id)}>
                  Obriši zakrpu
                </button>
              </>
            )}
          </div>
        )}
        <span className="divider" />
        <Menu label="Blokovi" icon={<Boxes size={16} aria-hidden />}>
          <button type="button" disabled={selectedIds.length < 2} onClick={() => merge.mutate(selectedIds)}>
            Spoji
          </button>
          <button type="button" disabled={selectedIds.length !== 1} onClick={() => duplicate.mutate(selectedIds[0])}>
            Dupliraj
          </button>
          <button type="button" disabled={selectedIds.length === 0} onClick={() => remove.mutate(selectedIds)}>
            Obriši
          </button>
          <button type="button" disabled={blocks.length < 2} onClick={() => autoOrder.mutate()}>
            Automatski redosled
          </button>
        </Menu>
        <div className="toolbar-group">
          <button
            type="button"
            aria-label="Obradi stranicu"
            disabled={processing || processMutation.isPending || !activeModel || page.skip}
            title={page.skip ? "Stranica je označena za preskakanje" : "Pronađi blokove i pročitaj ih (OCR)"}
            onClick={() =>
              (blocks.length === 0 || window.confirm("Postojeći blokovi na ovoj stranici biće zamenjeni. Nastaviti?")) &&
              processMutation.mutate()
            }
          >
            <ScanText size={16} aria-hidden />
            Obradi
          </button>
          <Menu label="OCR" title="OCR: model i čitanje izabranih blokova">
            <label className="field">
              OCR model
              <select
                aria-label="OCR model"
                value={activeModel ?? ""}
                onChange={(event) => {
                  setOcrModel(event.target.value);
                  saveSetting("striptrans.ocrModel", event.target.value);
                }}
              >
                {modelNames.length === 0 && <option value="">nema vision modela</option>}
                {modelNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={autoOcr}
                onChange={(event) => {
                  setAutoOcr(event.target.checked);
                  saveSetting("striptrans.autoOcr", event.target.checked);
                }}
              />
              Čitaj nov blok
            </label>
            <button type="button" disabled={selectedIds.length === 0 || read.isPending || !activeModel} onClick={() => readBlocks(selectedIds)}>
              {read.isPending ? "Čitam…" : "Pročitaj (R)"}
            </button>
          </Menu>
        </div>
        <div className="toolbar-group">
          <button
            type="button"
            aria-label="Prevedi stranicu"
            title={`Prevedi stranicu (${activeTranslationModel ?? "nema modela"})`}
            disabled={processing || translatePageMutation.isPending || !activeTranslationModel || blocks.length === 0}
            onClick={() => translatePageMutation.mutate()}
          >
            <Languages size={16} aria-hidden />
            Prevedi
          </button>
          <Menu label="Prevod" title="Model prevoda">
            <label className="field">
              Model prevoda
              <select
                aria-label="Model prevoda"
                value={activeTranslationModel ?? ""}
                onChange={(event) => {
                  setTranslationModel(event.target.value);
                  saveSetting("striptrans.translationModel", event.target.value);
                }}
              >
                {translationNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </Menu>
        </div>
        <button
          type="button"
          aria-label="Očisti stranicu"
          disabled={processing || cleanMutation.isPending || blocks.length === 0}
          title="Obriši originalni tekst sa stranice"
          onClick={() => cleanMutation.mutate()}
        >
          <Eraser size={16} aria-hidden />
          Očisti
        </button>
        {pageJob.data && <JobStatus job={pageJob.data} onCancel={(id) => cancelMutation.mutate(id)} />}
        {mutationError && (
          <span className="error" title={mutationError.message}>
            {mutationError.message}
          </span>
        )}
        <span className="spacer" />
        <Menu label="Prikaz" icon={<Eye size={16} aria-hidden />} align="right">
          <label>
            <input type="checkbox" checked={showBlocks} onChange={(event) => setShowBlocks(event.target.checked)} />
            Prikaži blokove
          </label>
          <label>
            <input type="checkbox" checked={showLettering} onChange={(event) => setShowLettering(event.target.checked)} />
            Prevod na slici
          </label>
          <label title={page.cleaned_at ? "" : "Stranica još nije očišćena"}>
            <input type="checkbox" checked={showClean && !!page.cleaned_at} disabled={!page.cleaned_at} onChange={(event) => setShowClean(event.target.checked)} />
            Očišćeno
          </label>
          {references.length > 0 && (
            <label>
              <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
              Uporedo sa referencom
            </label>
          )}
          <label>
            <input type="checkbox" checked={onlyWarnings} onChange={(event) => setOnlyWarnings(event.target.checked)} />
            Samo upozorenja ({warned.size})
          </label>
        </Menu>
        <Menu label="Fontovi" icon={<CaseSensitive size={16} aria-hidden />} align="right">
          <label className="field">
            Govor, misli, naracija
            <select aria-label="Font za govor" value={dialogueFont?.key ?? ""} onChange={(event) => seriesFonts.mutate({ dialogue_font: event.target.value })}>
              {fontList
                .filter((font) => font.kind === "dialogue")
                .map((font) => (
                  <option key={font.key} value={font.key}>
                    {font.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="field">
            Onomatopeje
            <select aria-label="Font za onomatopeje" value={soundFont?.key ?? ""} onChange={(event) => seriesFonts.mutate({ sfx_font: event.target.value })}>
              {fontList.map((font) => (
                <option key={font.key} value={font.key}>
                  {font.name}
                </option>
              ))}
            </select>
          </label>
          <label title="Kao u srpskim izdanjima: sva naracija ukošena (bez podebljanja). Važi za ceo serijal i izvoz.">
            <input type="checkbox" checked={!!series?.caption_italic} onChange={(event) => seriesFonts.mutate({ caption_italic: event.target.checked })} />
            Naracija ukošena
          </label>
          <label className="button" title="TTF ili OTF; mora imati Č Ć Ž Š Đ">
            Dodaj font…
            <input
              type="file"
              accept=".ttf,.otf,font/ttf,font/otf"
              aria-label="Dodaj font"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) addFont.mutate(file);
                event.target.value = "";
              }}
            />
          </label>
          {addFont.isError && <span className="error">{addFont.error.message}</span>}
        </Menu>
        <Menu label="Sačuvaj" icon={<Download size={16} aria-hidden />} align="right" title="Stranica u punoj rezoluciji, kao u izvozu">
          <label className="field">
            Format slike
            <select aria-label="Format slike" value={saveFormat} onChange={(event) => setSaveFormat(event.target.value as ImageFormat)}>
              <option value="jpeg">JPG</option>
              <option value="png">PNG</option>
            </select>
          </label>
          <button type="button" disabled={!pageLettering || savePage.isPending} onClick={() => savePage.mutate()}>
            {savePage.isPending ? "Čuvam…" : "Sačuvaj stranicu"}
          </button>
        </Menu>
      </div>
      <div className={`editor-body${showPanel ? "" : " no-panel"}`}>
        <div className={`canvases${showReference ? " split" : ""}`}>
          <PageCanvas
            viewKey={page.id}
            url={showClean && page.cleaned_at ? pageCleanUrl(page) : pageImageUrl(page.id, page.version)}
            lettering={lettering}
            editLettering={editLettering && !!lettering}
            onChangeLettering={changeStyle}
            blockText={(id) => blocks.find((block) => block.id === id)?.translation ?? ""}
            onChangeText={(id, translation) => changeBlock(id, { translation })}
            brush={brush}
            onBrushStroke={(stroke) => (stroke.mode.startsWith("patch-") ? patchMaskMutation.mutate(stroke) : maskMutation.mutate(stroke))}
            width={page.width}
            height={page.height}
            fit={fit}
            blocks={showBlocks ? blocks : undefined}
            selectedIds={selectedIds}
            drawMode={drawMode}
            onSelect={select}
            onChangeBlock={changeBlock}
            onCreateBlock={(rect) => create.mutate(rect)}
            patches={patches}
            editPatches={editPatches}
            selectedPatchId={selectedPatchId}
            onSelectPatch={setSelectedPatchId}
            onChangePatch={(id, changes) => changePatch({ id, changes })}
          />
          {showReference &&
            (reference ? (
              <PageCanvas viewKey={reference.id} url={pageImageUrl(reference.id, reference.version)} width={reference.width} height={reference.height} fit={fit} />
            ) : (
              <div className="page-canvas empty">Nema referentne stranice {position}</div>
            ))}
        </div>
        {showPanel && (
        <aside className="side-panel">
          <h2>Blokovi ({blocks.length})</h2>
          <BlockPanel
            blocks={onlyWarnings ? blocks.filter((block) => warned.has(block.id)) : blocks}
            selectedIds={selectedIds}
            onSelect={select}
            onUpdate={changeBlock}
            onMove={(id, delta) => reorder.mutate(moveBlock(blocks.map((block) => block.id), id, delta))}
            onDelete={(id) => remove.mutate([id])}
            readingIds={readingIds}
            onRead={(id) => readBlocks([id])}
            translatingIds={translatingIds}
            onTranslate={(id, shorter) => translate.mutate({ id, shorter })}
            reviews={reviews}
            onAddWord={(word) => addWord.mutate(word)}
            onConfirmSfx={(source, target) => confirmSfx.mutate({ source, target })}
            translationStyles={translationStyles.data ?? []}
            onPreview={(id, styleId) => previewTranslation(id, styleId)}
            onStyle={changeStyle}
            fonts={fontList}
            fits={overflows}
            onCutTitle={(id) => cutTitleMutation.mutate(id)}
            onSaveGlyph={(id, image, glyph, fill) => saveGlyph.mutateAsync({ id, image, glyph, fill })}
            onDeleteGlyph={(id, key) => deleteGlyph.mutate({ id, key })}
          />
        </aside>
        )}
      </div>
      {showStrip && (
      <div className="filmstrip">
        {originals.map((item) => (
          <Link
            key={item.id}
            to={`/projects/${projectId}/pages/${item.position}`}
            className={`${item.position === position ? "current" : ""}${item.translation_reviewed ? " reviewed" : ""}`}
            aria-label={`Stranica ${item.position}${item.translation_reviewed ? " (lektorisana)" : ""}`}
            aria-current={item.position === position ? "page" : undefined}
          >
            <img src={pageThumbnailUrl(item.id, item.version)} alt="" loading="lazy" />
            <span className="page-number">{item.position}</span>
          </Link>
        ))}
      </div>
      )}
    </div>
  );
}
