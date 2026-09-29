import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Rect } from "../api";
import { blocks, job, project, translationModels } from "../test/fixtures";
import { mockFetch, renderRoute } from "../test/utils";
import ViewerPage from "./ViewerPage";

// Konva traži pravi canvas, koga jsdom nema; mock samo prijavljuje URL i može da "nacrta" blok
const exportMocks = vi.hoisted(() => ({
  renderPage: vi.fn(async () => new Blob(["slika"], { type: "image/jpeg" })),
  downloadBlob: vi.fn(),
}));

vi.mock("../export/renderPage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../export/renderPage")>()),
  renderPage: exportMocks.renderPage,
  downloadBlob: exportMocks.downloadBlob,
}));

// prozor „Novo slovo" crta na canvas-u; ovde se proverava samo čuvanje kroz API
vi.mock("../components/GlyphEditor", () => ({
  default: ({ onSave, onClose }: { onSave: (image: Blob, glyph: object) => Promise<unknown>; onClose: () => void }) => (
    <button type="button" onClick={() => onSave(new Blob(["png"], { type: "image/png" }), { char: "K", baseline: 80, parts: [] }).then(onClose)}>
      mock-sačuvaj-slovo
    </button>
  ),
}));

vi.mock("../components/PageCanvas", () => ({
  default: ({
    url,
    onCreateBlock,
    brush,
    onBrushStroke,
    patches,
    editPatches,
    onSelectPatch,
    blockText,
    onChangeText,
    onSelect,
  }: {
    url: string;
    onSelect?: (id: number, add: boolean) => void;
    onCreateBlock?: (rect: Rect) => void;
    brush?: { mode: "add" | "erase"; radius: number } | null;
    onBrushStroke?: (stroke: { mode: "add" | "erase"; radius: number; points: [number, number][] }) => void;
    patches?: { id: number }[];
    editPatches?: boolean;
    onSelectPatch?: (id: number) => void;
    blockText?: (id: number) => string;
    onChangeText?: (id: number, text: string) => void;
  }) => (
    <div>
      <span data-testid="canvas-url">{url}</span>
      {onSelect && (
        <button type="button" onClick={() => onSelect(102, false)}>
          mock-izaberi-102
        </button>
      )}
      {onCreateBlock && (
        <button type="button" onClick={() => onCreateBlock({ x: 5, y: 6, width: 70, height: 40 })}>
          mock-nacrtaj
        </button>
      )}
      {brush && (
        <button type="button" onClick={() => onBrushStroke?.({ mode: brush.mode, radius: brush.radius, points: [[10, 20], [30, 40]] })}>
          mock-potez
        </button>
      )}
      {editPatches &&
        patches?.map((patch) => (
          <button key={patch.id} type="button" onClick={() => onSelectPatch?.(patch.id)}>
            mock-zakrpa-{patch.id}
          </button>
        ))}
      {onChangeText && (
        <>
          <span data-testid="canvas-text">{blockText?.(101)}</span>
          <button type="button" onClick={() => onChangeText(101, "NOVI PREVOD")}>
            mock-izmeni-tekst
          </button>
        </>
      )}
    </div>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const ocrModels = {
  default_model: "qwen2.5vl:7b",
  models: [
    { name: "qwen2.5vl:7b", size: 1, capabilities: ["vision"] },
    { name: "deepseek-ocr:3b", size: 1, capabilities: ["vision"] },
  ],
};

function renderEditor(position: number, extra: Record<string, unknown> = {}) {
  const fetchMock = mockFetch({
    "/api/projects/1": project,
    "GET /api/pages/11/blocks": blocks,
    "GET /api/pages/12/blocks": [],
    "GET /api/pages/13/blocks": [],
    "GET /api/pages/11/review": { page_id: 11, reviewed: false, blocks: [] },
    "GET /api/pages/12/review": { page_id: 12, reviewed: false, blocks: [] },
    "GET /api/pages/13/review": { page_id: 13, reviewed: false, blocks: [] },
    "GET /api/pages/11/patches": [],
    "GET /api/pages/12/patches": [],
    "GET /api/pages/13/patches": [],
    "GET /api/pages/11/history": { undo: null, redo: null },
    "GET /api/pages/12/history": { undo: null, redo: null },
    "GET /api/pages/13/history": { undo: null, redo: null },
    "GET /api/ocr/models": ocrModels,
    "GET /api/translation/models": translationModels,
    ...extra,
  });
  renderRoute("/projects/:projectId/pages/:position", `/projects/1/pages/${position}`, <ViewerPage />);
  return fetchMock;
}

/** Traka alata (Faza 7a): ređe radnje su u padajućim menijima. */
const openMenu = async (name: string) => userEvent.click(await screen.findByRole("button", { name }));

const canvasUrls = () => screen.getAllByTestId("canvas-url").map((canvas) => canvas.textContent);

function calls(fetchMock: ReturnType<typeof mockFetch>, method: string, url: string) {
  return fetchMock.mock.calls.filter(([callUrl, init]) => callUrl === url && (init?.method ?? "GET") === method);
}

describe("ViewerPage", () => {
  it("prikazuje original i referentnu stranicu uporedo", async () => {
    renderEditor(1);

    expect(await screen.findByTestId("page-indicator")).toHaveTextContent("1 / 3");
    expect(canvasUrls()).toEqual(["/api/pages/11/image", "/api/pages/21/image"]);
  });

  it("traka sličica ima brojeve stranica i ističe trenutnu", async () => {
    renderEditor(2);
    await screen.findByTestId("page-indicator");

    const current = screen.getByRole("link", { name: "Stranica 2" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: "Stranica 1" })).not.toHaveAttribute("aria-current");

    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("link", { name: "Stranica 3" })).toHaveAttribute("aria-current", "page");
  });

  it("menja stranice tastaturom", async () => {
    renderEditor(1);
    await screen.findByTestId("page-indicator");

    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("2 / 3");
    expect(screen.getByText("Nema referentne stranice 2")).toBeInTheDocument();

    await userEvent.keyboard("{End}");
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("3 / 3");
  });

  it("prikazuje blokove stranice u listi", async () => {
    renderEditor(1);

    expect(await screen.findByLabelText("Tekst bloka 1")).toHaveValue("L'UOMO CHE STAVATE\nASPETTANDO");
    expect(screen.getByLabelText("Tekst bloka 2")).toHaveValue("SCERIFFO!");
  });

  it("Esc prvo poništava selekciju, pa vraća na projekat", async () => {
    renderEditor(1);
    const item = await screen.findByTestId("block-101");

    await userEvent.click(item);
    expect(item).toHaveAttribute("aria-selected", "true");

    await userEvent.keyboard("{Escape}");
    expect(item).toHaveAttribute("aria-selected", "false");

    await userEvent.keyboard("{Escape}");
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/1");
  });

  it("Ctrl+Z poništava poslednju izmenu, dugme Ponovi je vraća", async () => {
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/history": { undo: "izmena bloka", redo: null },
      "POST /api/pages/11/undo": { action: "izmena bloka", undo: null, redo: "izmena bloka", blocks: [] },
      "POST /api/pages/11/redo": { action: "izmena bloka", undo: "izmena bloka", redo: null, blocks },
    });
    await screen.findByTestId("page-indicator");

    await userEvent.keyboard("{Control>}z{/Control}");

    expect(calls(fetchMock, "POST", "/api/pages/11/undo")).toHaveLength(1);
    expect(await screen.findByText("Poništeno: izmena bloka")).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "Ponovi" }));

    expect(calls(fetchMock, "POST", "/api/pages/11/redo")).toHaveLength(1);
    expect(await screen.findByText("Ponovljeno: izmena bloka")).toBeInTheDocument();
  });

  it("Poništi je isključeno kad istorija stranice je prazna", async () => {
    renderEditor(1);
    await screen.findByTestId("page-indicator");

    expect(screen.getByRole("button", { name: "Poništi" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ponovi" })).toBeDisabled();
  });

  it("režim Zakrpe: slika se dodaje preko stranice i nudi se izvoz isečka", async () => {
    const patch = { id: 7, position: 1, x: 10, y: 20, width: 100, height: 50, rotation: 0, opacity: 1, above_text: false, url: "/api/patches/7/image" };
    const fetchMock = renderEditor(1, { "POST /api/pages/11/patches": patch });
    await screen.findByTestId("page-indicator");

    await userEvent.click(screen.getByRole("button", { name: "Zakrpe (P)" }));
    const file = new File(["png"], "zakrpa.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("Dodaj zakrpu…"), file);

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/pages/11/patches")).toHaveLength(1));
    expect(screen.getByRole("link", { name: "Izvezi isečak" })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/pages/11/crop?x=0&y=0&width=1801&height=2457"),
    );
  });

  it("izabranoj zakrpi se menja providnost i može da se obriše", async () => {
    const patch = { id: 7, position: 1, x: 10, y: 20, width: 100, height: 50, rotation: 0, opacity: 1, above_text: false, url: "/api/patches/7/image" };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/patches": [patch],
      "PATCH /api/patches/7": { ...patch, opacity: 0.5 },
      "DELETE /api/patches/7": null,
    });
    await screen.findByTestId("page-indicator");
    await userEvent.click(screen.getByRole("button", { name: "Zakrpe (P)" }));

    await userEvent.click(await screen.findByRole("button", { name: "mock-zakrpa-7" }));
    fireEvent.change(screen.getByLabelText("Providnost zakrpe"), { target: { value: "50" } });

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/patches/7")).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Obriši zakrpu" }));

    await waitFor(() => expect(calls(fetchMock, "DELETE", "/api/patches/7")).toHaveLength(1));
  });

  it("strelice pomeraju izabrani blok (Shift za 10 px) i čuvaju jednom", async () => {
    const fetchMock = renderEditor(1, { "PATCH /api/blocks/101": blocks[0] });
    await userEvent.click(await screen.findByTestId("block-101"));

    await userEvent.keyboard("{Shift>}{ArrowRight}{ArrowRight}{/Shift}{ArrowDown}");

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/101")).toHaveLength(1), { timeout: 2000 });
    const body = JSON.parse(String(calls(fetchMock, "PATCH", "/api/blocks/101")[0][1]?.body));
    expect(body).toEqual({ x: blocks[0].x + 20, y: blocks[0].y + 1 });
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("1");
  });

  it("strelice pomeraju izabranu zakrpu", async () => {
    const patch = { id: 7, position: 1, x: 10, y: 20, width: 100, height: 50, rotation: 0, opacity: 1, above_text: false, url: "/api/patches/7/image" };
    const fetchMock = renderEditor(1, { "GET /api/pages/11/patches": [patch], "PATCH /api/patches/7": patch });
    await screen.findByTestId("page-indicator");
    await userEvent.click(screen.getByRole("button", { name: "Zakrpe (P)" }));
    await userEvent.click(await screen.findByRole("button", { name: "mock-zakrpa-7" }));

    await userEvent.keyboard("{ArrowLeft}{ArrowUp}{ArrowUp}");

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/patches/7")).toHaveLength(1), { timeout: 2000 });
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/patches/7")[0][1]?.body))).toEqual({ x: 9, y: 18 });
  });

  it("Delete briše izabrani blok", async () => {
    const fetchMock = renderEditor(1, { "DELETE /api/blocks/101": null });
    await userEvent.click(await screen.findByTestId("block-101"));

    await userEvent.keyboard("{Delete}");

    await waitFor(() => expect(calls(fetchMock, "DELETE", "/api/blocks/101")).toHaveLength(1));
  });

  it("čuva izmenjen tekst kad polje izgubi fokus", async () => {
    const fetchMock = renderEditor(1, { "PATCH /api/blocks/102": { ...blocks[1], text: "SCERIFFO!!" } });
    const textarea = await screen.findByLabelText("Tekst bloka 2");

    await userEvent.type(textarea, "!");
    await userEvent.tab();

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/102")).toHaveLength(1));
    const [, init] = calls(fetchMock, "PATCH", "/api/blocks/102")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ text: "SCERIFFO!!" });
  });

  it("povezuje blok sa nastavkom teksta u drugom bloku", async () => {
    const fetchMock = renderEditor(1, { "PATCH /api/blocks/101": { ...blocks[0], continues_id: 102 } });

    await userEvent.click(await screen.findByTestId("block-101"));
    await userEvent.selectOptions(screen.getByLabelText("Nastavak bloka 1"), "102");

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/101")).toHaveLength(1));
    const [, init] = calls(fetchMock, "PATCH", "/api/blocks/101")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ continues_id: 102 });
  });

  it("označava nastavak teksta i veza se vidi bez izbora bloka", async () => {
    renderEditor(1, { "GET /api/pages/11/blocks": [{ ...blocks[0], continues_id: 102 }, blocks[1]] });

    expect(await screen.findByText("nastavak bloka 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Nastavak bloka 1")).toHaveValue("102");
  });

  it("probni prevod izabranim stilom se prikazuje i upisuje tek na Primeni", async () => {
    const fetchMock = renderEditor(1, {
      "GET /api/translation-styles": [{ id: 2, name: "Moderni", text: "- SLENG.", builtin: false, active: false, changed: false }],
      "POST /api/blocks/101/translate/preview": { translation: "HAJDEMO!", note: "igra reči" },
      "PATCH /api/blocks/101": blocks[0],
    });
    await userEvent.click(await screen.findByTestId("block-101"));
    await userEvent.selectOptions(await screen.findByLabelText("Stil probnog prevoda bloka 1"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Probni prevod" }));

    expect(await screen.findByLabelText("Probni prevod bloka 1")).toHaveTextContent("HAJDEMO!");
    expect(screen.getByText("napomena prevodioca: igra reči")).toBeInTheDocument();
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/blocks/101/translate/preview")[0][1]?.body))).toEqual({ style_id: 2 });
    expect(calls(fetchMock, "PATCH", "/api/blocks/101")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Primeni" }));
    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/101")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/blocks/101")[0][1]?.body))).toEqual({ translation: "HAJDEMO!", translation_note: "igra reči" });
  });

  it("uz izabran blok kopira uputstvo za AI i zakrpu stavlja na mesto isečka", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const translated = { ...blocks[0], translation: "KRAŠ!" };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": [translated, blocks[1]],
      "GET /api/blocks/101/ai-prompt": { prompt: "Replace CRASH with KRAŠ" },
      "POST /api/pages/11/patches": { id: 9, position: 1, x: 90, y: 90, width: 220, height: 100, rotation: 0, opacity: 1, above_text: false, url: "/api/patches/9/image" },
    });
    await userEvent.click(await screen.findByTestId("block-101"));
    await userEvent.click(screen.getByRole("button", { name: "Zakrpe (P)" }));

    await userEvent.click(screen.getByRole("button", { name: "Kopiraj uputstvo za AI" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Replace CRASH with KRAŠ"));
    expect(screen.getByRole("link", { name: "Isečak originala za AI" }).getAttribute("href")).toContain("clean=false");

    const file = new File(["png"], "gemini.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText(/Zakrpa na blok 1/), file);
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/pages/11/patches")).toHaveLength(1));
    const body = calls(fetchMock, "POST", "/api/pages/11/patches")[0][1]?.body as FormData;
    // jsdom ne čita slike, pa zakrpa dobija ceo okvir isečka
    expect([body.get("x"), body.get("y"), body.get("width"), body.get("height"), body.get("match_page"), body.get("above_text")]).toEqual([
      "90",
      "90",
      "220",
      "100",
      "true",
      "true",
    ]);
  });

  it("blok izabran na slici se sam prikaže u panelu, a izbor u panelu ne pomera listu", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    // traka sličica takođe pomera trenutnu stranicu u vidno polje: brojimo samo blokove
    const scrolledBlocks = () => scroll.mock.contexts.filter((element) => (element as Element).matches?.("[data-testid^=block-]"));
    renderEditor(1);
    await userEvent.click(await screen.findByTestId("block-101"));
    expect(scrolledBlocks()).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "mock-izaberi-102" }));

    await waitFor(() => expect(scrolledBlocks()).toEqual([screen.getByTestId("block-102")]));
  });

  it("pravi nov blok iz nacrtanog pravougaonika", async () => {
    const created = { ...blocks[0], id: 103, position: 3 };
    const fetchMock = renderEditor(1, {
      "POST /api/pages/11/blocks": created,
      "POST /api/blocks/103/ocr": { ...created, text: "SCERIFFO!" },
    });
    await screen.findByTestId("block-101");

    await userEvent.click(screen.getByRole("button", { name: "Novi blok (N)" }));
    await userEvent.click(screen.getByRole("button", { name: "mock-nacrtaj" }));

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/pages/11/blocks")).toHaveLength(1));
    const [, init] = calls(fetchMock, "POST", "/api/pages/11/blocks")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ x: 5, y: 6, width: 70, height: 40 });
    // nov blok se odmah čita podrazumevanim modelom
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/blocks/103/ocr")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/blocks/103/ocr")[0][1]?.body))).toEqual({ model: "qwen2.5vl:7b" });
  });

  it("spaja blokove izabrane uz Shift", async () => {
    const user = userEvent.setup();
    const fetchMock = renderEditor(1, { "POST /api/pages/11/blocks/merge": [blocks[0]] });
    await user.click(await screen.findByTestId("block-101"));
    await user.keyboard("{Shift>}");
    await user.click(screen.getByTestId("block-102"));
    await user.keyboard("{/Shift}");

    await openMenu("Blokovi");
    await user.click(screen.getByRole("button", { name: "Spoji" }));

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/pages/11/blocks/merge")).toHaveLength(1));
    const [, init] = calls(fetchMock, "POST", "/api/pages/11/blocks/merge")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ block_ids: [101, 102] });
  });

  it("čita izabrane blokove izabranim modelom", async () => {
    const fetchMock = renderEditor(1, { "POST /api/blocks/101/ocr": { ...blocks[0], text: "L'UOMO CHE" } });
    await openMenu("OCR");
    await userEvent.selectOptions(await screen.findByLabelText("OCR model"), "deepseek-ocr:3b");
    await userEvent.click(screen.getByTestId("block-101")); // klik van menija ga zatvara

    await openMenu("OCR");
    await userEvent.click(screen.getByRole("button", { name: "Pročitaj (R)" }));

    expect(await screen.findByDisplayValue("L'UOMO CHE")).toBeInTheDocument();
    const [, init] = calls(fetchMock, "POST", "/api/blocks/101/ocr")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ model: "deepseek-ocr:3b" });
  });

  it("↻ u listi ponovo čita blok", async () => {
    const fetchMock = renderEditor(1, { "POST /api/blocks/102/ocr": blocks[1] });

    await userEvent.click(await screen.findByRole("button", { name: "Ponovo pročitaj blok 2" }));

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/blocks/102/ocr")).toHaveLength(1));
  });

  it("obrađuje stranicu i osvežava blokove kad posao završi", async () => {
    vi.stubGlobal("confirm", () => true);
    const fetchMock = renderEditor(1, {
      "POST /api/pages/11/process": job({ id: 7 }),
      "GET /api/jobs/7": job({ id: 7, status: "done", progress: 2, total: 2 }),
    });
    await openMenu("OCR");
    await screen.findByRole("option", { name: "qwen2.5vl:7b" });

    await userEvent.click(screen.getByRole("button", { name: "Obradi stranicu" }));

    expect(await screen.findByText("Obrada stranice: završeno")).toBeInTheDocument();
    const [, init] = calls(fetchMock, "POST", "/api/pages/11/process")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ model: "qwen2.5vl:7b" });
    await waitFor(() => expect(calls(fetchMock, "GET", "/api/pages/11/blocks").length).toBeGreaterThan(1));
  });

  it("prevodi blok i odobrava prevod", async () => {
    const translated = { ...blocks[1], translation: "ŠERIFE!", translation_status: "draft", translation_model: "gemma3:12b" };
    const fetchMock = renderEditor(1, {
      "POST /api/blocks/102/translate": translated,
      "PATCH /api/blocks/102": { ...translated, translation_status: "approved" },
    });
    await openMenu("Prevod");
    await screen.findByRole("option", { name: "gemma3:12b" });

    await userEvent.click(await screen.findByRole("button", { name: "Prevedi blok 2" }));

    expect(await screen.findByDisplayValue("ŠERIFE!")).toBeInTheDocument();
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/blocks/102/translate")[0][1]?.body))).toEqual({ model: "gemma3:12b", shorter: false });
    await userEvent.click(screen.getByRole("button", { name: "Odobri prevod bloka 2" }));
    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/102")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/blocks/102")[0][1]?.body))).toEqual({ translation_status: "approved" });
  });

  it("pokreće prevod cele stranice", async () => {
    const fetchMock = renderEditor(1, {
      "POST /api/pages/11/translate": job({ id: 8, type: "translate_page" }),
      "GET /api/jobs/8": job({ id: 8, type: "translate_page", status: "done" }),
    });
    await openMenu("Prevod");
    await screen.findByRole("option", { name: "gemma3:12b" });

    await userEvent.click(screen.getByRole("button", { name: "Prevedi stranicu" }));

    expect(await screen.findByText("Prevod stranice: završeno")).toBeInTheDocument();
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/pages/11/translate")[0][1]?.body))).toEqual({ model: "gemma3:12b" });
  });

  it("javlja kad stranica ne postoji", async () => {
    renderEditor(9);

    expect(await screen.findByText(/Stranica 9 ne postoji/)).toBeInTheDocument();
  });

  it("prikazuje upozorenja lekture i dodaje reč u rečnik", async () => {
    const review = {
      page_id: 11,
      reviewed: false,
      blocks: [
        { block_id: blocks[0].id, position: 1, unknown: ["GREJVUD"], glossary_missing: ["MIĆO"], non_serbian: ["TISUĆU"], too_long: false },
        {
          block_id: blocks[1].id,
          position: 2,
          unknown: [],
          glossary_missing: [],
          too_long: false,
          emphasis_missing: true,
          sfx_unconfirmed: [["SWISH", "SVIŠ"]],
        },
      ],
    };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/review": review,
      "POST /api/series/1/dictionary": { id: 5, series_id: 1, word: "grejvud" },
      "POST /api/sfx-glossary": { id: 9, source: "SWISH", target: "SVIŠ", note: null },
    });

    await userEvent.click(await screen.findByLabelText("Dodaj GREJVUD u rečnik"));
    await userEvent.click(screen.getByLabelText("Potvrdi SWISH → SVIŠ u glosaru onomatopeja"));
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/sfx-glossary")).toHaveLength(1));

    expect(screen.getByText("glosar: MIĆO")).toBeInTheDocument();
    expect(screen.getByText("nije srpski: TISUĆU")).toBeInTheDocument();
    expect(screen.getByText("naglasak nije prenet")).toBeInTheDocument();
    expect(calls(fetchMock, "POST", "/api/series/1/dictionary")).toHaveLength(1);
  });

  it("filtrira blokove na one sa upozorenjem", async () => {
    const review = {
      page_id: 11,
      reviewed: false,
      blocks: [
        { block_id: blocks[0].id, position: 1, unknown: ["GREJVUD"], glossary_missing: [], too_long: false },
        { block_id: blocks[1].id, position: 2, unknown: [], glossary_missing: [], too_long: false },
      ],
    };
    renderEditor(1, { "GET /api/pages/11/review": review });

    await openMenu("Prikaz");
    await userEvent.click(await screen.findByLabelText("Samo upozorenja (1)"));

    expect(screen.getByTestId(`block-${blocks[0].id}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`block-${blocks[1].id}`)).not.toBeInTheDocument();
  });

  it("Ctrl+Enter odobrava prevod i prelazi na sledeći blok", async () => {
    const translated = blocks.map((block) => ({ ...block, translation: "PREVOD", translation_status: "draft" as const }));
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      [`PATCH /api/blocks/${translated[0].id}`]: { ...translated[0], translation_status: "approved" },
    });
    await screen.findByTestId(`block-${translated[0].id}`);

    await userEvent.keyboard("{Control>}{Enter}{/Control}");

    expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(1);
    expect(await screen.findByTestId(`block-${translated[1].id}`)).toHaveAttribute("aria-selected", "true");
  });

  it("obeležava stranicu kao lektorisanu", async () => {
    const fetchMock = renderEditor(1, { "PATCH /api/pages/11": { ...project.pages[0], translation_reviewed: true } });

    await userEvent.click(await screen.findByLabelText("Stranica lektorisana"));

    expect(calls(fetchMock, "PATCH", "/api/pages/11")).toHaveLength(1);
  });

  it("čisti stranicu i prikazuje očišćenu sliku", async () => {
    const cleaned = { ...project, pages: project.pages.map((item) => (item.id === 11 ? { ...item, cleaned_at: "2026-09-18T10:00:00" } : item)) };
    const fetchMock = renderEditor(1, {
      "/api/projects/1": cleaned,
      "POST /api/pages/11/clean": job({ type: "clean_page" }),
    });

    await waitFor(() => expect(canvasUrls()[0]).toContain("/api/pages/11/clean-image?v="));
    await openMenu("Prikaz");
    await userEvent.click(screen.getByLabelText("Očišćeno"));
    expect(canvasUrls()[0]).toBe("/api/pages/11/image");

    await userEvent.click(screen.getByRole("button", { name: "Očisti stranicu" }));
    expect(calls(fetchMock, "POST", "/api/pages/11/clean")).toHaveLength(1);
  });

  it("prekidač očišćene slike je isključen dok stranica nije očišćena", async () => {
    renderEditor(1);

    await openMenu("Prikaz");
    expect(await screen.findByLabelText("Očišćeno")).toBeDisabled();
  });

  it("dodaje sopstveni font i postavlja ga za serijal", async () => {
    const font = { key: "user-1", name: "Ciao Mamma", kind: "dialogue", builtin: false, url: "/api/fonts/user-1/file" };
    const fetchMock = renderEditor(1, {
      "GET /api/fonts": [{ key: "comic-neue-bold", name: "Comic Neue Bold", kind: "dialogue", builtin: true, url: "/api/fonts/comic-neue-bold/file" }],
      "POST /api/fonts": font,
      "PATCH /api/series/1": { ...project.series, dialogue_font: "user-1" },
    });
    const file = new File(["font"], "ciao.ttf", { type: "font/ttf" });

    await openMenu("Fontovi");
    await userEvent.upload(await screen.findByLabelText("Dodaj font"), file);

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/series/1")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/series/1")[0][1]?.body))).toEqual({ dialogue_font: "user-1" });
  });

  it("naracija ukošena je opcija serijala u meniju Fontovi", async () => {
    const fetchMock = renderEditor(1, { "PATCH /api/series/1": { ...project.series, caption_italic: true } });

    await openMenu("Fontovi");
    await userEvent.click(await screen.findByLabelText("Naracija ukošena"));

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/series/1")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/series/1")[0][1]?.body))).toEqual({ caption_italic: true });
  });

  it("tekst se menja na samoj slici (dvoklik u bloku)", async () => {
    const translated = [{ ...blocks[0], translation: "STARI PREVOD", translation_status: "draft" as const }, blocks[1]];
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      "PATCH /api/blocks/101": { ...translated[0], translation: "NOVI PREVOD", translation_status: "edited" as const },
    });

    // canvas dobija tekući prevod bloka i vraća izmenjen
    await waitFor(() => expect(screen.getByTestId("canvas-text")).toHaveTextContent("STARI PREVOD"));
    await userEvent.click(screen.getByRole("button", { name: "mock-izmeni-tekst" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/blocks/101")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/blocks/101")[0][1]?.body))).toEqual({ translation: "NOVI PREVOD" });
  });

  it("ručno doteruje složen tekst izabranog bloka", async () => {
    const translated = blocks.map((block) => ({ ...block, translation: "PREVOD", translation_status: "draft" as const }));
    const styled = { ...translated[0], style: { scale: 1.05, dx: 0, dy: 0, rotation: 0, align: "center", line_spacing: 1, font: null } };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      [`PATCH /api/blocks/${translated[0].id}`]: styled,
    });
    await userEvent.click(await screen.findByTestId(`block-${translated[0].id}`));

    await userEvent.click(screen.getByRole("button", { name: "Veća slova (blok 1)" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(1));
    const body = JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)[0][1]?.body));
    expect(body.style.scale).toBe(1.05);
  });

  it("boja slova se bira iz palete ili slobodno (naslovna, kolor strane)", async () => {
    const translated = [{ ...blocks[0], translation: "PREVOD", translation_status: "draft" as const }, blocks[1]];
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      [`PATCH /api/blocks/${translated[0].id}`]: translated[0],
    });
    await userEvent.click(await screen.findByTestId(`block-${translated[0].id}`));

    await userEvent.click(screen.getByRole("button", { name: "Boja: žuta (blok 1)" }));
    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Obrub: izbor (blok 1)"), { target: { value: "#123456" } });
    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(2));

    const bodies = calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`).map((call) => JSON.parse(String(call[1]?.body)));
    expect(bodies[0].style.color).toBe("#ffd400");
    expect(bodies[1].style.outline_color).toBe("#123456");
  });

  it("vraća automatsko slaganje", async () => {
    const styled = { ...blocks[0], translation: "PREVOD", translation_status: "draft" as const, style: { scale: 1.2, dx: 5, dy: 0, rotation: 10, align: "left" as const, line_spacing: 1, font: null } };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": [styled, blocks[1]],
      [`PATCH /api/blocks/${styled.id}`]: { ...styled, style: null },
    });
    await userEvent.click(await screen.findByTestId(`block-${styled.id}`));

    expect(screen.getByRole("button", { name: "Ispravi rotaciju (blok 1)" })).toHaveTextContent("10° → 0°");
    await userEvent.click(screen.getByRole("button", { name: "Vrati automatsko slaganje (blok 1)" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${styled.id}`)).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${styled.id}`)[0][1]?.body))).toEqual({ style: null });
  });

  it("T uključuje uređivanje teksta na slici", async () => {
    renderEditor(1);
    const toggle = await screen.findByRole("button", { name: "Uredi tekst (T)" });

    await userEvent.keyboard("t");

    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("četkicom ispravlja masku čišćenja", async () => {
    const fetchMock = renderEditor(1, { "POST /api/pages/11/mask": { ...project.pages[0], cleaned_at: "2026-09-18T12:00:00" } });
    await screen.findByRole("button", { name: "Četkica (B)" });

    await userEvent.keyboard("b");
    await userEvent.selectOptions(screen.getByLabelText("Mod četkice"), "erase");
    await userEvent.click(screen.getByRole("button", { name: "mock-potez" }));

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/pages/11/mask")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/pages/11/mask")[0][1]?.body))).toEqual({
      strokes: [{ mode: "erase", radius: 12, points: [[10, 20], [30, 40]] }],
    });
  });

  it("četkicom briše deo zakrpe ispod poteza", async () => {
    const patch = { id: 7, position: 1, x: 0, y: 0, width: 100, height: 100, rotation: 0, opacity: 1, above_text: false, url: "/api/patches/7/image" };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/patches": [patch],
      "POST /api/patches/7/mask": { ...patch, url: "/api/patches/7/image?v=mask-1" },
    });
    await screen.findByRole("button", { name: "Četkica (B)" });

    await userEvent.keyboard("b");
    await userEvent.selectOptions(screen.getByLabelText("Mod četkice"), "patch-hide");
    await userEvent.click(screen.getByRole("button", { name: "mock-potez" }));

    await waitFor(() => expect(calls(fetchMock, "POST", "/api/patches/7/mask")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/patches/7/mask")[0][1]?.body))).toEqual({
      strokes: [{ mode: "hide", radius: 12, points: [[10, 20], [30, 40]] }],
    });
    expect(calls(fetchMock, "POST", "/api/pages/11/mask")).toHaveLength(0);
  });

  it("javlja kad potez za zakrpu nije počeo na zakrpi", async () => {
    renderEditor(1);
    await screen.findByRole("button", { name: "Četkica (B)" });

    await userEvent.keyboard("b");
    await userEvent.selectOptions(screen.getByLabelText("Mod četkice"), "patch-show");
    await userEvent.click(screen.getByRole("button", { name: "mock-potez" }));

    expect(await screen.findByText("Potez nije počeo na zakrpi.")).toBeInTheDocument();
  });

  it("čuva stranicu u punoj rezoluciji, očišćenu i sa prevodom", async () => {
    const cleaned = { ...project, pages: project.pages.map((item) => (item.id === 11 ? { ...item, cleaned_at: "2026-09-18T10:00:00" } : item)) };
    renderEditor(1, {
      "/api/projects/1": cleaned,
      "GET /api/fonts": [
        { key: "comic-neue-bold", name: "Comic Neue Bold", kind: "dialogue", builtin: true, url: "/api/fonts/comic-neue-bold/file" },
        { key: "bangers", name: "Bangers", kind: "sfx", builtin: true, url: "/api/fonts/bangers/file" },
      ],
    });
    await openMenu("Sačuvaj");
    const button = await screen.findByRole("button", { name: "Sačuvaj stranicu" });
    await waitFor(() => expect(button).toBeEnabled());

    await userEvent.click(button);

    await waitFor(() => expect(exportMocks.downloadBlob).toHaveBeenCalledTimes(1));
    const [options] = exportMocks.renderPage.mock.calls[0] as unknown as [{ imageUrl: string; width: number; format: string }];
    expect(options.imageUrl).toContain("/api/pages/11/clean-image");
    expect(options.format).toBe("jpeg");
    expect(exportMocks.downloadBlob.mock.calls[0][1]).toBe("ramon-12-001.jpg");
  });

  it("poravnava tekst obostrano", async () => {
    const translated = blocks.map((block) => ({ ...block, translation: "PREVOD", translation_status: "draft" as const }));
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      [`PATCH /api/blocks/${translated[0].id}`]: translated[0],
    });
    await userEvent.click(await screen.findByTestId(`block-${translated[0].id}`));

    await userEvent.click(screen.getByRole("button", { name: "Poravnaj obostrano (blok 1)" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)[0][1]?.body)).style.align).toBe("justify");
  });

  it("naglasak: ceo blok prekidačem, a reč dugmetom B ili sa Ctrl+B", async () => {
    const translated = blocks.map((block) => ({ ...block, translation: "NEKU VRSTU ORLA!", translation_status: "draft" as const }));
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": translated,
      [`PATCH /api/blocks/${translated[0].id}`]: translated[0],
    });
    await userEvent.click(await screen.findByTestId(`block-${translated[0].id}`));

    await userEvent.click(screen.getByRole("button", { name: "Naglašeno (blok 1)" }));
    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${translated[0].id}`)[0][1]?.body)).style.emphasis).toBe(true);

    const field = screen.getByLabelText("Prevod bloka 1") as HTMLTextAreaElement;
    field.focus();
    field.setSelectionRange(12, 12); // kursor u reči ORLA
    await userEvent.click(screen.getByRole("button", { name: "Naglasi reč u prevodu bloka 1" }));
    expect(field.value).toBe("NEKU VRSTU *ORLA*!");
    field.setSelectionRange(1, 1);
    await userEvent.keyboard("{Control>}b{/Control}");
    expect(field.value).toBe("*NEKU* VRSTU *ORLA*!");
  });

  it("AI prepravka natpisa: plaćen predlog se bira i prihvata besplatno, nov se traži posebno", async () => {
    const sign = [{ ...blocks[0], kind: "other" as const, text: "SHERIFF", translation: "ŠERIF", translation_status: "draft" as const }, blocks[1]];
    const proposal = (id: number, cost: number) => ({ job_id: id, model: "or:google/gemini-3.1-flash-image", cost, created_at: "2026-09-25T10:00:00" });
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": sign,
      [`GET /api/blocks/${sign[0].id}/ai-proposals`]: [proposal(8, 0.068), proposal(7, 0.034)],
      [`POST /api/blocks/${sign[0].id}/ai-patch`]: { id: 9, type: "ai_patch", status: "queued", project_id: 1, progress: 0, total: 0, cancel_requested: false, error: null, result: null, created_at: "", updated_at: "" },
      "POST /api/jobs/7/ai-accept": { id: 3, page_id: 11, position: 1, x: 100, y: 100, width: 200, height: 80, rotation: 0, opacity: 1, above_text: true },
    });
    await userEvent.click(await screen.findByTestId(`block-${sign[0].id}`));

    // najnoviji plaćen predlog se prikazuje odmah, uz original
    expect(await screen.findByAltText("Predlog AI prepravke")).toHaveAttribute("src", "/api/jobs/8/ai-image");
    expect(screen.getByAltText("Original").getAttribute("src")).toContain("clean=false");
    await userEvent.click(screen.getByRole("button", { name: "Predlog 7 (blok 1)" }));
    expect(screen.getByAltText("Predlog AI prepravke")).toHaveAttribute("src", "/api/jobs/7/ai-image");

    await userEvent.click(screen.getByRole("button", { name: "Prihvati AI prepravku (blok 1)" }));
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/jobs/7/ai-accept")).toHaveLength(1));
    expect(calls(fetchMock, "POST", `/api/blocks/${sign[0].id}/ai-patch`)).toHaveLength(0); // bez novog plaćanja

    await userEvent.click(screen.getByRole("button", { name: "Prepravi AI-jem (blok 1)" }));
    await waitFor(() => expect(calls(fetchMock, "POST", `/api/blocks/${sign[0].id}/ai-patch`)).toHaveLength(1));
  });

  it("naslov: bira drugi primerak slova i ponovo seče slova", async () => {
    const glyph = (key: string, char: string, source: "original" | "fallback" = "original") => ({
      key,
      char,
      source,
      width: 60,
      height: 80,
      baseline: 78,
      ink_left: 3,
      ink_right: 57,
      row: 0,
      gap_next: -2,
    });
    const title = {
      version: "v1",
      text: "PASSACRO!",
      light: true,
      ink: 255,
      background: 0,
      left: 100,
      top: 100,
      right: 600,
      bottom: 180,
      cap_height: 76,
      max_scale: 1.2,
      gap: -2,
      word_gap: 30,
      found: 9,
      expected: 9,
      glyphs: [..."PASSACRO!"].map((char, i) => glyph(`g${i}`, char)),
      extra: [glyph("x0", "K", "fallback")],
      font: "Archivo Black",
      fonts: ["Archivo Black", "Anton", "VC Ramon naslovi"],
    };
    const titled = { ...blocks[0], kind: "title" as const, text: "PASSACRO!", translation: "PASAKR!", translation_status: "draft" as const, title };
    const fetchMock = renderEditor(1, {
      "GET /api/pages/11/blocks": [titled, blocks[1]],
      [`PATCH /api/blocks/${titled.id}`]: titled,
      [`POST /api/blocks/${titled.id}/title`]: titled,
      [`POST /api/blocks/${titled.id}/glyphs`]: titled,
    });
    await userEvent.click(await screen.findByTestId(`block-${titled.id}`));

    const letters = within(screen.getByRole("group", { name: "Slova naslova (blok 1)" })).getAllByRole("button");
    expect(letters.map((letter) => letter.getAttribute("title"))[4]).toBe("K: napravljeno (nema ga u originalu)");
    await userEvent.click(letters[3]); // drugo A: drugi primerak originala (g4)
    await userEvent.click(screen.getByRole("button", { name: "Drugi primerak slova (blok 1)" }));
    await userEvent.click(screen.getByRole("button", { name: "Iseci slova naslova (blok 1)" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${titled.id}`)).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${titled.id}`)[0][1]?.body)).style.letters).toEqual({ "3": { key: "g1" } });
    await waitFor(() => expect(calls(fetchMock, "POST", `/api/blocks/${titled.id}/title`)).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Novo slovo od delova (blok 1)" }));
    await userEvent.click(screen.getByRole("button", { name: "mock-sačuvaj-slovo" }));
    await waitFor(() => expect(calls(fetchMock, "POST", `/api/blocks/${titled.id}/glyphs`)).toHaveLength(1));
    const body = calls(fetchMock, "POST", `/api/blocks/${titled.id}/glyphs`)[0][1]?.body as FormData;
    expect([body.get("char"), body.get("baseline"), body.get("parts")]).toEqual(["K", "80", "[]"]);

    await userEvent.click(letters[4]); // K: napravljeno, bira mu se font
    await userEvent.selectOptions(screen.getByLabelText("Font slova K (blok 1)"), "VC Ramon naslovi");
    await waitFor(() => expect(calls(fetchMock, "PATCH", `/api/blocks/${titled.id}`)).toHaveLength(2));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", `/api/blocks/${titled.id}`)[1][1]?.body)).style.letter_fonts).toEqual({ K: "VC Ramon naslovi" });
  });

  it("režimi rada isključuju jedan drugi, a panel i sličice se sakrivaju", async () => {
    renderEditor(1);
    const brush = await screen.findByRole("button", { name: "Četkica (B)" });

    await userEvent.click(brush);
    await userEvent.click(screen.getByRole("button", { name: "Novi blok (N)" }));

    expect(brush).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Novi blok (N)" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("Mod četkice")).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Izbor" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Panel blokova" }));
    await userEvent.click(screen.getByRole("button", { name: "Sličice stranica" }));
    expect(screen.queryByText(/^Blokovi \(/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Stranica 2" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("striptrans.showPanel") ?? "true")).toBe(false);
  });
});

