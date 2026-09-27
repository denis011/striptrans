import type { GlossaryEntry, Job, OcrModels, Page, ProjectDetail, Series, TextBlock } from "../api";

export const ramon: Series = { id: 1, name: "Ramon", source_lang: "it", target_lang: "sr" };

function page(id: number, kind: Page["kind"], position: number): Page {
  return { id, kind, position, import_order: position, source_name: `${position}.jpg`, width: 1801, height: 2457, skip: false, ocr_reviewed: false, translation_reviewed: false };
}

export const project: ProjectDetail = {
  id: 1,
  series: ramon,
  issue_number: "12",
  original_title: "Passacro!",
  translated_title: "Pasakr",
  created_at: "2026-09-15T10:00:00",
  page_count: 3,
  reference_page_count: 1,
  cover_page_id: 11,
  pages: [page(11, "original", 1), page(12, "original", 2), page(13, "original", 3), page(21, "reference", 1)],
  jobs: [],
  progress: {
    pages: 3,
    skipped: [],
    with_blocks: 2,
    unread: 0,
    blocks: 10,
    translation: { none: 4, draft: 5, approved: 1 },
    proofread: 1,
    cleaned: 0,
    exported_at: null,
    changed_at: null,
  },
};

function block(id: number, position: number, text: string): TextBlock {
  const rect = { x: 100 * position, y: 100, width: 200, height: 80 };
  const ocr = { ocr_text: null, confidence: null, ocr_model: null, bubble_polygon: null };
  const translation = { translation: "", translation_model: null, translation_status: "none" as const, translation_too_long: false };
  return { id, page_id: 11, position, kind: "speech", text, source: "manual", needs_review: false, ...rect, ...ocr, ...translation };
}

export const blocks: TextBlock[] = [block(101, 1, "L'UOMO CHE STAVATE\nASPETTANDO"), block(102, 2, "SCERIFFO!")];

export const ocrModels: OcrModels = {
  default_model: "qwen2.5vl:7b",
  models: [
    { name: "qwen2.5vl:7b", size: 1, capabilities: ["vision"] },
    { name: "deepseek-ocr:3b", size: 1, capabilities: ["vision"] },
  ],
};

export function job(overrides: Partial<Job>): Job {
  const base = { id: 7, type: "process_page", status: "queued" as const, project_id: 1, progress: 0, total: 0 };
  return { ...base, cancel_requested: false, error: null, result: null, created_at: "", updated_at: "", ...overrides };
}

export function glossaryEntry(overrides: Partial<GlossaryEntry>): GlossaryEntry {
  const base = { id: 1, series_id: 1, source: "MICO", target: "MIĆO", kind: "name" as const, note: null };
  return { ...base, status: "approved", origin: "manual", occurrences: 0, ...overrides };
}

export const translationModels: OcrModels = {
  default_model: "gemma3:12b",
  models: [{ name: "gemma3:12b", size: 1, capabilities: ["completion"] }],
};
