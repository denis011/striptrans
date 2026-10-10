import { Copy, ExternalLink, Image as ImageIcon, Scissors } from "lucide-react";
import { type Page, type Patch, type Rect, type TextBlock, getAiPrompt, pageCropUrl, updatePatch } from "../api";

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
}

interface Props {
  page: Page;
  cropSource: TextBlock | undefined; // izabran blok: zakrpa i isečak idu na njegovo mesto
  cropBox: Rect;
  selectedPatch: Patch | null;
  onAdd: (file: File) => void;
  onChange: (id: number, changes: Parameters<typeof updatePatch>[1]) => void;
  onRemove: (id: number) => void;
  onNote: (note: string) => void;
}

/** Alatke režima Zakrpe: slika preko stranice, isečak za doradu i ručni AI tok (Gemini). */
export default function PatchTools({ page, cropSource, cropBox, selectedPatch, onAdd, onChange, onRemove, onNote }: Props) {
  const copyAiPrompt = async () => {
    if (!cropSource) return;
    try {
      const { prompt } = await getAiPrompt(cropSource.id);
      await navigator.clipboard.writeText(prompt);
      onNote("Uputstvo je kopirano: nalepi ga u AI aplikaciju (Ctrl+V), a sliku koju vrati kopiraj i nalepi ovde (Ctrl+V)");
    } catch (error) {
      onNote(`Uputstvo nije kopirano: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  // ručni AI tok bez fajlova: isečak originala ide u clipboard (Ctrl+V u AI aplikaciji), a slika koju
  // aplikacija vrati se lepi u editor (Ctrl+V) i postaje zakrpa na izabranom bloku
  const prepareForAi = async () => {
    if (!cropSource) return;
    const url = pageCropUrl(page.id, cropBox, false);
    try {
      // Promise<Blob> čuva dozvolu klika dok se isečak preuzima (Safari i Chrome)
      const png = fetch(url).then((response) => response.blob());
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      onNote(
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
      onNote("Isečak je preuzet kao fajl (pregledač ne dozvoljava sliku u clipboard-u)");
    }
    // Gemini prekida vezu sa tabom koji ga otvori (Cross-Origin-Opener-Policy), pa ga aplikacija ne može
    // pronaći ni prebaciti u prvi plan: otvara se samo prvi put u sesiji, dalje ga korisnik bira sam
    if (!aiTabOpened()) openAiApp();
  };

  return (
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
            if (file) onAdd(file);
            event.target.value = "";
          }}
        />
      </label>
      <a
        className="button"
        title="Isečak izabranog bloka (ili cele stranice) u punoj rezoluciji, za doradu van aplikacije"
        href={pageCropUrl(page.id, cropBox, !!page.cleaned_at)}
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
            onChange={(event) => onChange(selectedPatch.id, { opacity: Number(event.target.value) / 100 })}
          />
          <label title="Zakrpa se crta i preko složenog prevoda">
            <input
              type="checkbox"
              checked={selectedPatch.above_text}
              onChange={(event) => onChange(selectedPatch.id, { above_text: event.target.checked })}
            />
            Iznad teksta
          </label>
          <button type="button" onClick={() => onRemove(selectedPatch.id)}>
            Obriši zakrpu
          </button>
        </>
      )}
    </div>
  );
}
