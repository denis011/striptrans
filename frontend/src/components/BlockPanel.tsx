import { useRef, useState } from "react";
import {
  type BlockChanges,
  type BlockKind,
  type BlockReview,
  type FontInfo,
  type LetterStyle,
  type LetteringStyle,
  type TextBlock,
  type TitleGlyph,
  type TranslationStatus,
  titleGlyphUrl,
} from "../api";
import { BLOCK_KINDS, kindColor } from "../editor/blocks";
import { blockStyle } from "../lettering/blocks";
import { emphasizeSelection, isEmphasisKey } from "../lettering/emphasisInput";
import { choicesFor, composeTitle } from "../lettering/title";
import AiPatch, { AI_KINDS } from "./AiPatch";
import GlyphEditor, { type SavedGlyph } from "./GlyphEditor";

interface Props {
  blocks: TextBlock[];
  selectedIds: number[];
  onSelect: (id: number, additive: boolean) => void;
  onUpdate: (id: number, changes: BlockChanges) => void;
  onMove: (id: number, delta: number) => void;
  onDelete: (id: number) => void;
  readingIds: number[];
  onRead: (id: number) => void;
  translatingIds: number[];
  onTranslate: (id: number, shorter: boolean) => void;
  reviews?: Record<number, BlockReview>;
  onAddWord?: (word: string) => void;
  onConfirmSfx?: (source: string, target: string) => void;
  onStyle?: (id: number, changes: Partial<LetteringStyle> | null) => void;
  fonts?: FontInfo[];
  fits?: Record<number, { line: number; extra: number } | null>; // blokovi čiji tekst ne staje
  onCutTitle?: (id: number) => void;
  onSaveGlyph?: (id: number, image: Blob, glyph: SavedGlyph, fill?: Blob) => Promise<unknown>;
  onDeleteGlyph?: (id: number, key: string) => void;
}

const round = (value: number) => Math.round(value * 100) / 100;

// boje koje se najčešće traže na naslovnoj i kolor stranama; ostalo se bira slobodno
const SWATCHES = [
  { color: "#ffffff", name: "bela" },
  { color: "#000000", name: "crna" },
  { color: "#ffd400", name: "žuta" },
  { color: "#d7261e", name: "crvena" },
];
const EDGE_STEP = 0.02; // debljina obruba, u veličinama slova
const COVER_EDGE = 0.3; // „Prekrij original": obrub dovoljno debeo da sakrije stara slova ispod novih

/** Boja slova i obruba bloka (naslovna, kolor strane); „A" vraća automatsku boju. */
function ColorControls({ block, set }: { block: TextBlock; set: (changes: Partial<LetteringStyle>) => void }) {
  const style = blockStyle(block);
  const label = (text: string) => `${text} (blok ${block.position})`;
  const edgeWidth = style.outline_width ?? (style.outline_color || block.kind === "sfx" ? 0.12 : 0);
  const row = (field: "color" | "outline_color", title: string) => (
    <div className="color-row">
      <span className="detail">{title}</span>
      <button
        type="button"
        className={`small${style[field] ? "" : " active"}`}
        aria-label={label(`${title}: automatski`)}
        title="Automatski: crno, a belo na tamnoj podlozi"
        onClick={() => set({ [field]: null })}
      >
        A
      </button>
      {SWATCHES.map((swatch) => (
        <button
          key={swatch.color}
          type="button"
          className={`swatch${style[field] === swatch.color ? " active" : ""}`}
          style={{ background: swatch.color }}
          aria-label={label(`${title}: ${swatch.name}`)}
          title={swatch.name}
          onClick={() => set({ [field]: swatch.color })}
        />
      ))}
      <input
        type="color"
        aria-label={label(`${title}: izbor`)}
        value={style[field] ?? "#000000"}
        onChange={(event) => set({ [field]: event.target.value })}
      />
    </div>
  );
  const coverable = block.kind === "sfx" || block.kind === "other";
  return (
    <div className="color-controls">
      {coverable && (
        <label
          className="detail"
          title="Original se ne briše (brisanje preko gustog crteža ume da bude ružno), već ga nova slova prekriju debelim obrubom boje papira. Važi posle „Očisti stranicu“; ostatke dočisti četkicom."
        >
          <input
            type="checkbox"
            aria-label={label("Prekrij original")}
            checked={style.cover ?? false}
            onChange={(event) => set({ cover: event.target.checked, outline_width: event.target.checked ? COVER_EDGE : null })}
          />{" "}
          Prekrij original (bez brisanja)
        </label>
      )}
      {row("color", "Boja")}
      {row("outline_color", "Obrub")}
      <div className="color-row">
        <span className="detail">Debljina obruba</span>
        <button
          type="button"
          className="small"
          aria-label={label("Tanji obrub")}
          disabled={edgeWidth <= 0}
          onClick={() => set({ outline_width: round(Math.max(0, edgeWidth - EDGE_STEP)) })}
        >
          −
        </button>
        <span className="detail">{Math.round(edgeWidth * 100)}%</span>
        <button
          type="button"
          className="small"
          aria-label={label("Deblji obrub")}
          onClick={() => set({ outline_width: round(Math.min(0.5, edgeWidth + EDGE_STEP)) })}
        >
          +
        </button>
      </div>
    </div>
  );
}

/** Ručno doterivanje složenog teksta izabranog bloka. */
function StyleControls({ block, onStyle, fonts }: { block: TextBlock; onStyle: NonNullable<Props["onStyle"]>; fonts: FontInfo[] }) {
  const style = blockStyle(block);
  const label = (text: string) => `${text} (blok ${block.position})`;
  const set = (changes: Partial<LetteringStyle>) => onStyle(block.id, changes);
  return (
    <div className="style-controls" onClick={(event) => event.stopPropagation()}>
      <button type="button" className="small" aria-label={label("Manja slova")} onClick={() => set({ scale: round(Math.max(0.3, style.scale - 0.05)) })}>
        A−
      </button>
      <span className="detail" title="Veličina slova u odnosu na automatsku">
        {Math.round(style.scale * 100)}%
      </span>
      <button type="button" className="small" aria-label={label("Veća slova")} onClick={() => set({ scale: round(Math.min(3, style.scale + 0.05)) })}>
        A+
      </button>
      <button type="button" className="small" aria-label={label("Manji prored")} title="Prored" onClick={() => set({ line_spacing: round(Math.max(0.5, style.line_spacing - 0.05)) })}>
        ≡−
      </button>
      <button type="button" className="small" aria-label={label("Veći prored")} title="Prored" onClick={() => set({ line_spacing: round(Math.min(2, style.line_spacing + 0.05)) })}>
        ≡+
      </button>
      {(["left", "center", "right", "justify"] as const).map((align) => (
        <button
          key={align}
          type="button"
          className={`small${style.align === align ? " active" : ""}`}
          aria-pressed={style.align === align}
          aria-label={label({ left: "Poravnaj levo", center: "Centriraj", right: "Poravnaj desno", justify: "Poravnaj obostrano" }[align])}
          title={align === "justify" ? "Razvuci redove između leve i desne ivice (poslednji red ostaje centriran)" : undefined}
          onClick={() => set({ align })}
        >
          {{ left: "⇤", center: "↔", right: "⇥", justify: "☰" }[align]}
        </button>
      ))}
      {style.rotation !== 0 && (
        <button type="button" className="small" aria-label={label("Ispravi rotaciju")} onClick={() => set({ rotation: 0 })}>
          {style.rotation}° → 0°
        </button>
      )}
      <select aria-label={label("Font bloka")} value={style.font ?? ""} onChange={(event) => set({ font: event.target.value || null })}>
        <option value="">font serijala</option>
        {fonts.map((font) => (
          <option key={font.key} value={font.key}>
            {font.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        className={`small${style.emphasis ? " active" : ""}`}
        aria-pressed={!!style.emphasis}
        aria-label={label("Naglašeno")}
        title="Ceo oblačić podebljan i ukošen (vika, psovka), kao u srpskim izdanjima. Za jednu reč: dugme B uz prevod ili Ctrl+B."
        onClick={() => set({ emphasis: !style.emphasis })}
      >
        Naglašeno
      </button>
      <button
        type="button"
        className={`small${style.fill_box ? " active" : ""}`}
        aria-pressed={!!style.fill_box}
        aria-label={label("Uklopi u okvir")}
        title="Za uredničke strane i impresum: tekst puni okvir bloka, a veličina slova se bira slobodno (A−/A+ je smanjuje ili povećava)"
        onClick={() => set({ fill_box: !style.fill_box, scale: 1 })}
      >
        Uklopi u okvir
      </button>
      <button type="button" className="small" aria-label={label("Vrati automatsko slaganje")} disabled={!block.style} onClick={() => onStyle(block.id, null)}>
        Automatski
      </button>
      <ColorControls block={block} set={set} />
    </div>
  );
}

const NUDGE = 0.02; // pomeraj slova naslova, u visinama slova
const TURN = 3; // rotacija slova naslova, u stepenima
const SOURCE_NOTE = {
  original: "slovo originala",
  accent: "slovo originala sa dodatim znakom",
  fallback: "napravljeno (nema ga u originalu)",
  custom: "sastavljeno od delova originala",
} as const;

/** Naslov od slova originala: veličina, razmak, izbor primerka i pomeraj pojedinačnih slova. */
function TitleControls({
  block,
  onStyle,
  onCutTitle,
  onSaveGlyph,
  onDeleteGlyph,
}: {
  block: TextBlock;
  onStyle: NonNullable<Props["onStyle"]>;
  onCutTitle?: Props["onCutTitle"];
  onSaveGlyph?: Props["onSaveGlyph"];
  onDeleteGlyph?: Props["onDeleteGlyph"];
}) {
  const [current, setCurrent] = useState<number | null>(null);
  const [editor, setEditor] = useState<{ char: string; editing?: TitleGlyph } | null>(null);
  const style = blockStyle(block);
  const title = block.title;
  const label = (text: string) => `${text} (blok ${block.position})`;
  const set = (changes: Partial<LetteringStyle>) => onStyle(block.id, changes);
  const cut = onCutTitle && (
    <button type="button" className="small" aria-label={label("Iseci slova naslova")} onClick={() => onCutTitle(block.id)}>
      Iseci slova ponovo
    </button>
  );
  if (!title?.glyphs.length) {
    return (
      <div className="style-controls" onClick={(event) => event.stopPropagation()}>
        <span className="warning">Slova naslova nisu nađena u okviru bloka.</span>
        {cut}
      </div>
    );
  }
  const composed = composeTitle(block.translation, title, style);
  const letter = composed.letters.find((item) => item.index === current);
  const own: LetterStyle = (current !== null && style.letters[String(current)]) || {};
  const setLetter = (changes: LetterStyle | null) => {
    if (current === null) return;
    const letters = { ...style.letters };
    if (changes === null) delete letters[String(current)];
    else letters[String(current)] = { ...own, ...changes };
    set({ letters });
  };
  const choices = letter ? choicesFor(title, letter.char) : [];
  const nextChoice = () => {
    const at = choices.findIndex((glyph) => glyph.key === letter?.key);
    setLetter({ key: choices[(at + 1) % choices.length].key });
  };
  const nudge = (axis: "dx" | "dy", delta: number) => setLetter({ [axis]: round((own[axis] ?? 0) + delta) });
  const customGlyph = letter?.source === "custom" ? title.custom?.find((glyph) => glyph.key === letter.key) : undefined;
  // slovo kojeg nema u originalu pravi se od fonta: automatski najsličnijeg, ili izabranog
  const chosenFonts = style.letter_fonts ?? {};
  // slovo kojeg nema u originalu (i kad je izabran primerak sastavljen od delova)
  const madeGlyph = letter && letter.source !== "original" ? title.extra.find((glyph) => glyph.char === letter.char) : undefined;
  const setLetterFont = (char: string, font: string) => {
    const letter_fonts = { ...chosenFonts };
    if (font) letter_fonts[char] = font;
    else delete letter_fonts[char];
    // izabran font se vidi tek na napravljenom primerku, pa slovo prelazi na njega
    const letters = { ...style.letters };
    if (current !== null && madeGlyph) letters[String(current)] = { ...own, key: madeGlyph.key };
    set({ letter_fonts, letters });
  };
  return (
    <div className="style-controls title-controls" onClick={(event) => event.stopPropagation()}>
      {title.found !== title.expected && (
        <span className="warning">
          Nađeno {title.found} slova, a tekst originala ima {title.expected} — ispravi tekst ili okvir bloka.
        </span>
      )}
      {composed.missing.length > 0 && <span className="warning">Nema slova za: {composed.missing.join(" ")}</span>}
      <div className="title-letters" role="group" aria-label={label("Slova naslova")}>
        {composed.letters.map((item) => (
          <button
            key={item.index}
            type="button"
            className={`title-letter source-${item.source}${item.index === current ? " active" : ""}`}
            aria-pressed={item.index === current}
            title={`${item.char}: ${SOURCE_NOTE[item.source]}`}
            onClick={() => setCurrent(item.index === current ? null : item.index)}
          >
            <img src={titleGlyphUrl(block.id, title, item.key)} alt={item.char} />
          </button>
        ))}
      </div>
      {letter && (
        <div className="toolbar-group">
          <span className="detail">
            {letter.char}: {SOURCE_NOTE[letter.source]}
          </span>
          <button type="button" className="small" disabled={choices.length < 2} onClick={nextChoice} aria-label={label("Drugi primerak slova")}>
            Drugi primerak ({choices.findIndex((glyph) => glyph.key === letter.key) + 1}/{choices.length})
          </button>
          <button type="button" className="small" aria-label={label("Slovo levo")} onClick={() => nudge("dx", -NUDGE)}>
            ←
          </button>
          <button type="button" className="small" aria-label={label("Slovo desno")} onClick={() => nudge("dx", NUDGE)}>
            →
          </button>
          <button type="button" className="small" aria-label={label("Slovo gore")} onClick={() => nudge("dy", -NUDGE)}>
            ↑
          </button>
          <button type="button" className="small" aria-label={label("Slovo dole")} onClick={() => nudge("dy", NUDGE)}>
            ↓
          </button>
          <button type="button" className="small" aria-label={label("Rotiraj slovo ulevo")} title="Rotacija slova (npr. naslov u luku)" onClick={() => setLetter({ rotation: Math.max(-90, (own.rotation ?? 0) - TURN) })}>
            ↺
          </button>
          <button type="button" className="small" aria-label={label("Rotiraj slovo udesno")} title="Rotacija slova (npr. naslov u luku)" onClick={() => setLetter({ rotation: Math.min(90, (own.rotation ?? 0) + TURN) })}>
            ↻
          </button>
          <button type="button" className="small" disabled={current === null || !style.letters[String(current)]} onClick={() => setLetter(null)}>
            Poništi slovo
          </button>
          {customGlyph && onSaveGlyph && (
            <button type="button" className="small" onClick={() => setEditor({ char: customGlyph.char, editing: customGlyph })}>
              Uredi slovo
            </button>
          )}
          {madeGlyph && !title.fonts?.length && <span className="detail">Za izbor fonta slova: „Iseci slova ponovo"</span>}
          {madeGlyph && (title.fonts?.length ?? 0) > 0 && (
            <label className="detail">
              Font slova{" "}
              <select
                aria-label={label(`Font slova ${letter.char}`)}
                value={chosenFonts[letter.char] ?? ""}
                onChange={(event) => setLetterFont(letter.char, event.target.value)}
              >
                <option value="">Automatski ({title.font})</option>
                {title.fonts!.map((font) => (
                  <option key={font} value={font}>
                    {font}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
      {onSaveGlyph && (
        <div className="toolbar-group">
          <button type="button" className="small" aria-label={label("Novo slovo od delova")} title="Sastavi slovo od delova slova originala (npr. K od R)" onClick={() => setEditor({ char: letter?.char ?? composed.letters.find((item) => item.source === "fallback")?.char ?? "" })}>
            Novo slovo od delova…
          </button>
          {title.font && <span className="detail">napravljena slova: {title.font}</span>}
        </div>
      )}
      {editor && onSaveGlyph && (
        <GlyphEditor
          block={block}
          char={editor.char}
          editing={editor.editing}
          onSave={(image, glyph, fill) => onSaveGlyph(block.id, image, glyph, fill)}
          onDelete={
            editor.editing && onDeleteGlyph
              ? () => {
                  onDeleteGlyph(block.id, editor.editing!.key);
                  setEditor(null);
                }
              : undefined
          }
          onClose={() => setEditor(null)}
        />
      )}
      <div className="toolbar-group">
        <label>
          <input type="checkbox" checked={style.fit === "fill"} onChange={(event) => set({ fit: event.target.checked ? "fill" : "original" })} /> Popuni širinu
        </label>
        <label title="Unutrašnjost slova (papir) pokriva crtež iza slova, kao u originalu">
          <input type="checkbox" aria-label={label("Neprovidna slova")} checked={style.opaque ?? !!title.hollow} onChange={(event) => set({ opaque: event.target.checked })} /> Neprovidna
        </label>
        <button type="button" className="small" aria-label={label("Manja slova")} onClick={() => set({ scale: round(Math.max(0.3, style.scale - 0.05)) })}>
          A−
        </button>
        <span className="detail" title="Veličina u odnosu na automatsku">
          {Math.round(style.scale * 100)}%
        </span>
        <button type="button" className="small" aria-label={label("Veća slova")} onClick={() => set({ scale: round(Math.min(3, style.scale + 0.05)) })}>
          A+
        </button>
        <button type="button" className="small" aria-label={label("Manji razmak slova")} title="Razmak slova" onClick={() => set({ letter_spacing: round(Math.max(-0.5, style.letter_spacing - NUDGE)) })}>
          razmak −
        </button>
        <button type="button" className="small" aria-label={label("Veći razmak slova")} title="Razmak slova" onClick={() => set({ letter_spacing: round(Math.min(1, style.letter_spacing + NUDGE)) })}>
          razmak +
        </button>
        {style.rotation !== 0 && (
          <button type="button" className="small" aria-label={label("Ispravi rotaciju")} onClick={() => set({ rotation: 0 })}>
            {style.rotation}° → 0°
          </button>
        )}
        <button type="button" className="small" aria-label={label("Vrati automatsko slaganje")} disabled={!block.style} onClick={() => onStyle(block.id, null)}>
          Automatski
        </button>
        {cut}
      </div>
    </div>
  );
}

function Warnings({
  review,
  onAddWord,
  onConfirmSfx,
}: {
  review?: BlockReview;
  onAddWord?: (word: string) => void;
  onConfirmSfx?: (source: string, target: string) => void;
}) {
  const foreign = review?.non_serbian ?? [];
  const sounds = review?.sfx_unconfirmed ?? [];
  if (
    !review ||
    (review.unknown.length === 0 &&
      review.glossary_missing.length === 0 &&
      foreign.length === 0 &&
      !review.emphasis_missing &&
      !review.maybe_continues &&
      sounds.length === 0)
  )
    return null;
  return (
    <div className="warnings">
      {review.maybe_continues && (
        <span className="badge warning" title="Naracija se završava usred rečenice: ako se nastavlja u drugoj koloni, izaberi taj blok u „Nastavlja se u“, pa se prevodi u jednom komadu">
          nastavlja se?
        </span>
      )}
      {sounds.map(([source, target]) => (
        <button
          key={`sfx-${source}`}
          type="button"
          className="badge warning"
          title="Nije u glosaru onomatopeja (predlog po pravilu ili produžen oblik) — klikni da potvrdiš i dodaš u glosar; drugi zapis upiši u prevod"
          aria-label={`Potvrdi ${source} → ${target} u glosaru onomatopeja`}
          onClick={(event) => {
            event.stopPropagation();
            onConfirmSfx?.(source, target);
          }}
        >
          {source} → {target} ✓
        </button>
      ))}
      {review.unknown.map((word) => (
        <button
          key={word}
          type="button"
          className="badge warning"
          title="Nema u rečniku — klikni da dodaš"
          aria-label={`Dodaj ${word} u rečnik`}
          onClick={(event) => {
            event.stopPropagation();
            onAddWord?.(word);
          }}
        >
          {word} +
        </button>
      ))}
      {foreign.map((word) => (
        <span key={`hr-${word}`} className="badge warning" title="Hrvatska ili ijekavska reč — u srpskom prevodu ide drugi oblik">
          nije srpski: {word}
        </span>
      ))}
      {review.glossary_missing.map((term) => (
        <span key={term} className="badge warning" title="Glosar traži ovaj izraz">
          glosar: {term}
        </span>
      ))}
      {review.emphasis_missing && (
        <span className="badge warning" title="Reči označene *zvezdicama* u originalu su podebljane; označi iste reči u prevodu (Ctrl+B)">
          naglasak nije prenet
        </span>
      )}
    </div>
  );
}

const TRANSLATION_STATUS: Record<TranslationStatus, string> = {
  none: "bez prevoda",
  draft: "nacrt",
  edited: "izmenjeno",
  approved: "odobreno",
};

function TranslationText({ block, onSave }: { block: TextBlock; onSave: (translation: string) => void }) {
  const [draft, setDraft] = useState(block.translation);
  const field = useRef<HTMLTextAreaElement>(null);
  const emphasize = () => field.current && emphasizeSelection(field.current, setDraft);
  return (
    <div className="translation-field">
      <textarea
        ref={field}
        className="translation-text"
        aria-label={`Prevod bloka ${block.position}`}
        value={draft}
        rows={Math.max(2, Math.ceil(draft.length / 32))}
        placeholder="(bez prevoda)"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => draft !== block.translation && onSave(draft)}
        onKeyDown={(event) => {
          if (!isEmphasisKey(event)) return;
          event.preventDefault();
          emphasize();
        }}
      />
      <button
        type="button"
        className="small emphasis-button"
        aria-label={`Naglasi reč u prevodu bloka ${block.position}`}
        title="Naglasi označenu reč (podebljano i ukošeno, kao u srpskim izdanjima), ili reč pod kursorom — Ctrl+B. U prevodu se piše *REČ*."
        // polje ne sme da izgubi izbor pre klika
        onMouseDown={(event) => event.preventDefault()}
        onClick={(event) => {
          event.stopPropagation();
          emphasize();
        }}
      >
        <strong>B</strong>
      </button>
    </div>
  );
}

function BlockText({ block, onSave }: { block: TextBlock; onSave: (text: string) => void }) {
  const [draft, setDraft] = useState(block.text);
  return (
    <textarea
      aria-label={`Tekst bloka ${block.position}`}
      value={draft}
      rows={Math.max(2, draft.split("\n").length)}
      placeholder="(bez teksta)"
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => draft !== block.text && onSave(draft)}
    />
  );
}

export default function BlockPanel({
  blocks,
  selectedIds,
  onSelect,
  onUpdate,
  onMove,
  onDelete,
  readingIds,
  onRead,
  translatingIds,
  onTranslate,
  reviews,
  onAddWord,
  onConfirmSfx,
  onStyle,
  fonts = [],
  fits,
  onCutTitle,
  onSaveGlyph,
  onDeleteGlyph,
}: Props) {
  if (blocks.length === 0) {
    return <p className="detail">Nema blokova. Uključi „Novi blok" (N) i prevuci pravougaonik preko teksta.</p>;
  }
  return (
    <ol className="block-list">
      {blocks.map((block, index) => {
        const selected = selectedIds.includes(block.id);
        const stop = (action: () => void) => (event: React.MouseEvent) => {
          event.stopPropagation();
          action();
        };
        return (
          <li
            key={block.id}
            data-testid={`block-${block.id}`}
            aria-selected={selected}
            className={selected ? "selected" : ""}
            style={{ borderLeftColor: kindColor(block.kind) }}
            onClick={(event) => onSelect(block.id, event.shiftKey || event.ctrlKey || event.metaKey)}
          >
            <div className="block-head">
              <strong>{block.position}</strong>
              <select
                aria-label={`Tip bloka ${block.position}`}
                value={block.kind}
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => {
                  const kind = event.target.value as BlockKind;
                  // ručno slaganje teksta ne važi za slova naslova (i obrnuto)
                  const reset = (kind === "title") !== (block.kind === "title") && block.style;
                  onUpdate(block.id, reset ? { kind, style: null } : { kind });
                }}
              >
                {BLOCK_KINDS.map((item) => (
                  <option key={item.kind} value={item.kind}>
                    {item.label}
                  </option>
                ))}
              </select>
              {blocks
                .filter((other) => other.continues_id === block.id)
                .map((other) => (
                  <span key={`nastavak-${other.id}`} className="badge" title="Prevodi se zajedno sa prethodnim delom teksta">
                    nastavak bloka {other.position}
                  </span>
                ))}
              {block.needs_review && <span className="badge">za proveru</span>}
              {readingIds.includes(block.id) && <span className="badge">čitam…</span>}
              <span className="block-actions">
                <button
                  type="button"
                  className="icon"
                  aria-label={`Ponovo pročitaj blok ${block.position}`}
                  title={block.ocr_model ? `Pročitao ${block.ocr_model}` : "Pročitaj"}
                  disabled={readingIds.includes(block.id)}
                  onClick={stop(() => onRead(block.id))}
                >
                  ↻
                </button>
                <button type="button" className="icon" aria-label={`Pomeri blok ${block.position} gore`} disabled={index === 0} onClick={stop(() => onMove(block.id, -1))}>
                  ↑
                </button>
                <button type="button" className="icon" aria-label={`Pomeri blok ${block.position} dole`} disabled={index === blocks.length - 1} onClick={stop(() => onMove(block.id, 1))}>
                  ↓
                </button>
                <button type="button" className="icon" aria-label={`Obriši blok ${block.position}`} onClick={stop(() => onDelete(block.id))}>
                  ✕
                </button>
              </span>
            </div>
            <BlockText key={`tekst:${block.id}:${block.text}`} block={block} onSave={(text) => onUpdate(block.id, { text })} />
            <div className="translation-head">
              <span className={`translation-status status-${block.translation_status}`}>{TRANSLATION_STATUS[block.translation_status]}</span>
              {block.translation_too_long && <span className="badge">predugačko</span>}
              {translatingIds.includes(block.id) && <span className="badge">prevodim…</span>}
              <span className="block-actions">
                <button type="button" className="small" aria-label={`Prevedi blok ${block.position}`} disabled={translatingIds.includes(block.id)} onClick={stop(() => onTranslate(block.id, false))}>
                  Prevedi
                </button>
                <button type="button" className="small" aria-label={`Skrati prevod bloka ${block.position}`} disabled={!block.translation || translatingIds.includes(block.id)} onClick={stop(() => onTranslate(block.id, true))}>
                  Kraće
                </button>
                <button type="button" className="small" aria-label={`Odobri prevod bloka ${block.position}`} disabled={!block.translation || block.translation_status === "approved"} onClick={stop(() => onUpdate(block.id, { translation_status: "approved" }))}>
                  ✓
                </button>
              </span>
            </div>
            <TranslationText key={`prevod:${block.id}:${block.translation}`} block={block} onSave={(translation) => onUpdate(block.id, { translation })} />
            <Warnings review={reviews?.[block.id]} onAddWord={onAddWord} onConfirmSfx={onConfirmSfx} />
            {(selected || block.continues_id) && (
              <label className="continues" onClick={(event) => event.stopPropagation()}>
                Nastavlja se u{" "}
                <select
                  aria-label={`Nastavak bloka ${block.position}`}
                  value={block.continues_id ?? ""}
                  onChange={(event) => onUpdate(block.id, { continues_id: event.target.value ? Number(event.target.value) : null })}
                >
                  <option value="">— (samostalan tekst)</option>
                  {blocks
                    .filter((other) => other.id !== block.id)
                    .map((other) => (
                      <option key={other.id} value={other.id}>
                        {other.position}: {other.text.replace(/\s+/g, " ").slice(0, 30)}
                      </option>
                    ))}
                </select>
              </label>
            )}
            {selected && onStyle && block.kind === "title" && <TitleControls block={block} onStyle={onStyle} onCutTitle={onCutTitle} onSaveGlyph={onSaveGlyph} onDeleteGlyph={onDeleteGlyph} />}
            {selected && block.id in (fits ?? {}) && (
              <span className="warning">
                {fits?.[block.id]
                  ? `Tekst ne staje: ${fits[block.id]!.line}. red je širi od oblačića za ${fits[block.id]!.extra} px. Smanji slova, prelomi red drugačije ili skrati prevod.`
                  : "Tekst ne staje u oblačić po visini. Smanji slova ili skrati prevod."}
              </span>
            )}
            {selected && onStyle && block.kind !== "title" && block.translation && <StyleControls block={block} onStyle={onStyle} fonts={fonts} />}
            {selected && AI_KINDS.has(block.kind) && block.translation && block.text && <AiPatch block={block} />}
          </li>
        );
      })}
    </ol>
  );
}
