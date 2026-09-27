import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { job, ocrModels, project, translationModels } from "../test/fixtures";
import { mockFetch, renderRoute } from "../test/utils";
import ProjectPage from "./ProjectPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderProject(data = project) {
  const fetchMock = mockFetch({
    "GET /api/projects/1": data,
    "DELETE /api/pages/11": null,
    "PATCH /api/pages/11": { ...data.pages[0], skip: true },
    "POST /api/projects/1/pages/reset-order": [],
    "GET /api/ocr/models": ocrModels,
    "GET /api/translation/models": translationModels,
  });
  renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);
  return fetchMock;
}

describe("ProjectPage", () => {
  it("prikazuje korake obrade redom, sa stanjem svakog koraka", async () => {
    renderProject();
    await screen.findByRole("heading", { name: "Ramon 12 — Pasakr" });

    const steps = within(screen.getByRole("list", { name: "Koraci obrade" })).getAllByRole("listitem");

    expect(steps).toHaveLength(8);
    expect(steps[0]).toHaveTextContent("1. Uvezi stranice");
    expect(steps[0]).toHaveTextContent("3 originala · 1 reference");
    expect(steps[2]).toHaveTextContent("2 od 3 stranica");
    expect(steps[3]).toHaveTextContent("4 bez prevoda · 5 nacrta · 1 odobreno");
    expect(steps[4]).toHaveTextContent("1 od 3 stranica lektorisano");
    expect(steps[7]).toHaveTextContent("još nije izvezen");
    expect(steps[0]).toHaveClass("done"); // uvoz je gotov, prevod nije
    expect(steps[3]).not.toHaveClass("done");
  });

  it("korak 8 pokazuje izvoz u toku: crtanje, pa upozorenje kad je tab zatvoren", async () => {
    const drawing = { stage: "drawing" as const, done: 34, total: 98, stale: true };
    renderProject({ ...project, progress: { ...project.progress, export_active: drawing } });

    const bar = await screen.findByTestId("export-active");
    expect(bar).toHaveTextContent("Crtam stranice: 34 / 98 — čeka otvoren tab za izvoz");
    expect(within(bar).getByRole("progressbar")).toHaveAttribute("value", "34");
  });

  it('dugme „Ponovo izmeri oblačiće" traži posao za ceo projekat', async () => {
    const cleaned = { ...project, progress: { ...project.progress, cleaned: 3 } };
    const fetchMock = mockFetch({
      "GET /api/projects/1": cleaned,
      "GET /api/ocr/models": ocrModels,
      "GET /api/translation/models": translationModels,
      "POST /api/projects/1/shapes": job({ type: "reshape_project" }),
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Ponovo izmeri oblačiće" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) => url === "/api/projects/1/shapes" && init?.method === "POST",
        ),
      ).toHaveLength(1),
    );
  });

  it("dok nijedna strana nije očišćena, ponovno merenje oblačića nije moguće", async () => {
    renderProject();  // progress.cleaned = 0

    expect(await screen.findByRole("button", { name: "Ponovo izmeri oblačiće" })).toBeDisabled();
  });

  it("izvoz stariji od poslednje izmene nije označen kao gotov", async () => {
    const progress = { ...project.progress, exported_at: "2026-09-18T21:11:13", changed_at: "2026-09-20T10:00:00" };
    renderProject({ ...project, progress });
    await screen.findByRole("heading", { name: "Ramon 12 — Pasakr" });

    const exportStep = within(screen.getByRole("list", { name: "Koraci obrade" })).getAllByRole("listitem")[7];

    expect(exportStep).toHaveTextContent("album je menjan posle toga");
    expect(exportStep).not.toHaveClass("done");
  });

  it("stranica se preskače iz spiska sličica", async () => {
    const fetchMock = renderProject();
    await screen.findByRole("heading", { name: "Ramon 12 — Pasakr" });

    await userEvent.click(screen.getByRole("button", { name: "Preskoči stranicu 1" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/pages/11",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ skip: true }) }),
      ),
    );
  });

  it("nudi scenario za lektora u oba formata", async () => {
    renderProject();
    await screen.findByRole("heading", { name: "Ramon 12 — Pasakr" });

    expect(screen.getByRole("link", { name: "Scenario" })).toHaveAttribute(
      "href",
      "/api/projects/1/script?format=html",
    );
    expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute("href", "/api/projects/1/script?format=csv");
  });

  it("prikazuje sličice originala i reference po tabovima", async () => {
    renderProject();

    expect(await screen.findByRole("heading", { name: "Ramon 12 — Pasakr" })).toBeInTheDocument();
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("alt"))).toEqual([
      "Stranica 1",
      "Stranica 2",
      "Stranica 3",
    ]);

    expect(screen.queryByTestId("order-notice")).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: "Referenca (1)" }));
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });

  it("prikazuje napredak uvoza koji je u toku", async () => {
    const job = { id: 5, type: "import", status: "running", progress: 40, total: 100 };
    renderProject({ ...project, jobs: [job as never] });

    expect(await screen.findByTestId("job-progress")).toHaveTextContent("Uvoz: 40 / 100");
  });

  it("briše stranicu posle potvrde", async () => {
    vi.stubGlobal("confirm", () => true);
    const fetchMock = renderProject();

    await userEvent.click(await screen.findByRole("button", { name: "Obriši stranicu 1" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/pages/11" && init?.method === "DELETE")).toBe(true),
    );
  });

  it("označava izmenjen raspored i vraća izvorni redosled", async () => {
    vi.stubGlobal("confirm", () => true);
    const swap: Record<number, number> = { 11: 2, 12: 1 };
    const pages = project.pages.map((page) => ({ ...page, position: swap[page.id] ?? page.position }));
    const fetchMock = renderProject({ ...project, pages });

    expect(await screen.findByTestId("order-notice")).toHaveTextContent("Raspored stranica je izmenjen: original");
    expect(screen.getByRole("tab", { name: "Original (3) •" })).toBeInTheDocument();
    expect(screen.getByText("(izv. 1)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Vrati izvorni redosled" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url === "/api/projects/1/pages/reset-order" && init?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("pokreće obradu celog projekta sa izabranim modelom", async () => {
    const fetchMock = mockFetch({
      "GET /api/projects/1": project,
      "GET /api/ocr/models": ocrModels,
      "POST /api/projects/1/process": job({ type: "process_project" }),
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);
    await screen.findByRole("option", { name: "deepseek-ocr:3b" });

    await userEvent.selectOptions(screen.getByLabelText("OCR model za obradu"), "deepseek-ocr:3b");
    await userEvent.click(screen.getByLabelText(/Zameni/));
    await userEvent.click(screen.getByRole("button", { name: "Obradi ceo projekat" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/projects/1/process")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => url === "/api/projects/1/process") ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({ model: "deepseek-ocr:3b", replace: true });
  });

  it("prikazuje obradu u toku i može da je prekine", async () => {
    const running = job({ id: 9, type: "process_project", status: "running", progress: 3, total: 100 });
    const fetchMock = mockFetch({
      "GET /api/projects/1": { ...project, jobs: [running] },
      "GET /api/ocr/models": ocrModels,
      "POST /api/jobs/9/cancel": { ...running, cancel_requested: true },
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);

    expect(await screen.findByTestId("job-progress")).toHaveTextContent("Obrada: 3 / 100");
    expect(screen.getByRole("button", { name: "Obradi ceo projekat" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Prekini" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/jobs/9/cancel")).toBe(true));
  });

  it("pokreće prevod celog projekta", async () => {
    const fetchMock = mockFetch({
      "GET /api/projects/1": project,
      "GET /api/ocr/models": ocrModels,
      "GET /api/translation/models": translationModels,
      "POST /api/projects/1/translate": job({ type: "translate_project" }),
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);
    await screen.findByRole("option", { name: "gemma3:12b" });

    await userEvent.click(screen.getByRole("button", { name: "Prevedi ceo projekat" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/projects/1/translate")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => url === "/api/projects/1/translate") ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({ model: "gemma3:12b", replace: false });
  });

  it("pokreće čišćenje celog projekta", async () => {
    const fetchMock = mockFetch({
      "/api/projects/1": project,
      "GET /api/ocr/models": ocrModels,
      "GET /api/translation/models": translationModels,
      "POST /api/projects/1/clean": job({ type: "clean_project" }),
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Očisti ceo projekat" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/projects/1/clean" && init?.method === "POST")).toBe(true));
  });

  it("pokreće pripremu celog albuma sa izabranim modelima", async () => {
    const fetchMock = mockFetch({
      "/api/projects/1": project,
      "GET /api/ocr/models": ocrModels,
      "GET /api/translation/models": translationModels,
      "POST /api/projects/1/prepare": job({ type: "prepare_project" }),
    });
    renderRoute("/projects/:projectId", "/projects/1", <ProjectPage />);
    await screen.findByRole("option", { name: "gemma3:12b" });

    await userEvent.click(screen.getByRole("button", { name: "Pripremi ceo album" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/projects/1/prepare")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => url === "/api/projects/1/prepare") ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({ ocr_model: "qwen2.5vl:7b", translation_model: "gemma3:12b" });
  });
});
