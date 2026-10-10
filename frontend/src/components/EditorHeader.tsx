import { Ban, Check, ChevronLeft, ChevronRight, FastForward, GalleryHorizontal, PanelRight } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { Link } from "react-router";
import { type Page, updatePage } from "../api";
import type { FitMode } from "../viewer/zoom";
import type { Fit } from "./PageCanvas";
import ThemeToggle from "./ThemeToggle";

const FIT_BUTTONS: [FitMode, string, string][] = [
  ["page", "Cela stranica", "Cela"],
  ["width", "Širina", "Širina"],
  ["actual", "100 %", "1:1"],
];

interface Props {
  projectId: number;
  title: string;
  position: number;
  count: number;
  importRank: number | undefined; // mesto stranice pri uvozu (pre preuređivanja)
  onGo: (position: number) => void;
  onPending: () => void;
  pendingCount: number; // neodobreni blokovi u albumu
  pendingOnPage: boolean;
  fit: Fit;
  onFit: Dispatch<SetStateAction<Fit>>;
  page: Page;
  onFlags: (changes: Parameters<typeof updatePage>[1]) => void;
  showStrip: boolean;
  onStrip: (show: boolean) => void;
  showPanel: boolean;
  onPanel: (show: boolean) => void;
}

/** Gornja traka editora: projekat, stranice, uklapanje, oznake stranice i prikaz panela. */
export default function EditorHeader({ projectId, title, position, count, importRank, onGo, onPending, pendingCount, pendingOnPage, fit, onFit, page, onFlags, showStrip, onStrip, showPanel, onPanel }: Props) {
  return (
    <header className="editor-header">
      <Link to="/" className="brand">
        StripTrans
      </Link>
      <span className="divider" />
      <Link to={`/projects/${projectId}`} className="project-link" title="Nazad na projekat (Esc)">
        ← {title}
      </Link>
      <div className="page-nav">
        <button type="button" className="icon-button" onClick={() => onGo(position - 1)} disabled={position <= 1} aria-label="Prethodna stranica" title="Prethodna stranica (←)">
          <ChevronLeft size={18} aria-hidden />
        </button>
        <span data-testid="page-indicator">
          {position} / {count}
        </span>
        <button type="button" className="icon-button" onClick={() => onGo(position + 1)} disabled={position >= count} aria-label="Sledeća stranica" title="Sledeća stranica (→)">
          <ChevronRight size={18} aria-hidden />
        </button>
        {importRank !== position && <span className="moved-from">(izvorno {importRank})</span>}
        <button
          type="button"
          className="icon-button"
          onClick={onPending}
          disabled={pendingCount === 0 && !pendingOnPage}
          aria-label="Sledeći neodobren blok"
          title={`Sledeći neodobren blok (U) — preostalo ${pendingCount}`}
        >
          <FastForward size={18} aria-hidden />
        </button>
      </div>
      <div className="segmented">
        {FIT_BUTTONS.map(([fitMode, label, short]) => (
          <button
            key={fitMode}
            type="button"
            aria-label={label}
            title={label}
            className={fit.mode === fitMode ? "active" : ""}
            onClick={() => onFit((current) => ({ mode: fitMode, token: current.token + 1 }))}
          >
            {short}
          </button>
        ))}
      </div>
      <span className="spacer" />
      <label className={`chip${page.ocr_reviewed ? " on" : ""}`} title="Tekst originala (OCR) na stranici je proveren">
        <input type="checkbox" aria-label="Stranica pregledana" checked={page.ocr_reviewed} onChange={(event) => onFlags({ ocr_reviewed: event.target.checked })} />
        {page.ocr_reviewed && <Check size={14} aria-hidden />} OCR proveren
      </label>
      <label className={`chip${page.translation_reviewed ? " on" : ""}`} title="Prevod na stranici je lektorisan (Ctrl+Shift+Enter)">
        <input type="checkbox" aria-label="Stranica lektorisana" checked={page.translation_reviewed} onChange={(event) => onFlags({ translation_reviewed: event.target.checked })} />
        {page.translation_reviewed && <Check size={14} aria-hidden />} Lektorisana
      </label>
      <label className={`chip skip${page.skip ? " on" : ""}`} title="Stranica se ne obrađuje (naslovna, reklama) i ulazi u album neizmenjena">
        <input type="checkbox" aria-label="Preskoči stranicu" checked={page.skip} onChange={(event) => onFlags({ skip: event.target.checked })} />
        {page.skip && <Ban size={14} aria-hidden />} Preskoči
      </label>
      <span className="divider" />
      <button
        type="button"
        className="icon-button"
        aria-pressed={showStrip}
        aria-label="Sličice stranica"
        title="Sličice stranica na dnu"
        onClick={() => onStrip(!showStrip)}
      >
        <GalleryHorizontal size={18} aria-hidden />
      </button>
      <button
        type="button"
        className="icon-button"
        aria-pressed={showPanel}
        aria-label="Panel blokova"
        title="Panel blokova desno"
        onClick={() => onPanel(!showPanel)}
      >
        <PanelRight size={18} aria-hidden />
      </button>
      <ThemeToggle />
    </header>
  );
}
