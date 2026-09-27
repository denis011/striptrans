import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { blocks, job, project } from "../test/fixtures";
import { mockFetch, renderRoute } from "../test/utils";
import ExportPage from "./ExportPage";

const renderMock = vi.hoisted(() => vi.fn(async () => new Blob(["png"], { type: "image/png" })));
vi.mock("../export/renderPage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../export/renderPage")>()),
  renderPage: renderMock,
}));

afterEach(() => {
  vi.unstubAllGlobals();
  renderMock.mockClear();
});

const fonts = [
  { key: "comic-neue-bold", name: "Comic Neue Bold", kind: "dialogue", builtin: true, url: "/api/fonts/comic-neue-bold/file" },
  { key: "bangers", name: "Bangers", kind: "sfx", builtin: true, url: "/api/fonts/bangers/file" },
];

const readiness = [
  { position: 1, page_id: 11, skip: false, cleaned: true, reviewed: true, blocks: 2, untranslated: 0 },
  { position: 2, page_id: 12, skip: true, cleaned: false, reviewed: false, blocks: 0, untranslated: 0 },
  { position: 3, page_id: 13, skip: false, cleaned: false, reviewed: false, blocks: 3, untranslated: 2 },
];

const created = {
  id: 5,
  project_id: 1,
  format: "cbz",
  image_format: "jpeg",
  quality: 92,
  skipped: "include",
  positions: [1, 2],
  received: [],
  status: "uploading",
  size: null,
  error: null,
  created_at: "2026-09-18T20:00:00",
  finished_at: null,
  pages: [
    { position: 1, page_id: 11, render: true },
    { position: 2, page_id: 12, render: false },
  ],
};

function renderExport(extra: Record<string, unknown> = {}) {
  const fetchMock = mockFetch({
    "/api/projects/1": project,
    "GET /api/projects/1/export-check": readiness,
    "GET /api/projects/1/exports": [],
    "GET /api/fonts": fonts,
    ...extra,
  });
  renderRoute("/projects/:projectId/export", "/projects/1/export", <ExportPage />);
  return fetchMock;
}

const calls = (fetchMock: ReturnType<typeof mockFetch>, method: string, url: string) =>
  fetchMock.mock.calls.filter(([callUrl, init]) => callUrl === url && (init?.method ?? "GET") === method);

describe("ExportPage", () => {
  it("prikazuje šta nije spremno, ali dozvoljava izvoz", async () => {
    renderExport();

    expect(await screen.findByText(/blokova bez prevoda: 2/)).toBeInTheDocument();
    expect(screen.getByText(/Stranice koje nisu gotove \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/nije očišćena, 2 bez prevoda, nije lektorisana/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Izvezi album" })).toBeEnabled();
  });

  it("crta samo nepreskočene stranice, šalje ih i pakuje album", async () => {
    const fetchMock = renderExport({
      "POST /api/projects/1/exports": created,
      "GET /api/pages/11/blocks": blocks,
      "GET /api/pages/11/patches": [],
      "PUT /api/exports/5/pages/1": { ...created, received: [1] },
      "POST /api/exports/5/finish": job({ id: 9, type: "export", status: "done" }),
    });
    await userEvent.selectOptions(await screen.findByLabelText("Format albuma"), "pdf");

    await userEvent.click(screen.getByRole("button", { name: "Izvezi album" }));

    expect(await screen.findByText(/Gotovo\./)).toBeInTheDocument();
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/projects/1/exports")[0][1]?.body))).toMatchObject({ format: "pdf", quality: 92, skipped: "include" });
    expect(renderMock).toHaveBeenCalledTimes(1); // preskočena stranica 2 se ne crta
    expect(calls(fetchMock, "PUT", "/api/exports/5/pages/1")).toHaveLength(1);
    expect(calls(fetchMock, "POST", "/api/exports/5/finish")).toHaveLength(1);
  });

  it("nudi preuzimanje gotovih izvoza", async () => {
    renderExport({ "GET /api/projects/1/exports": [{ ...created, status: "done", size: 5 * 1024 * 1024 }] });

    const link = await screen.findByRole("link", { name: "Preuzmi" });

    expect(link).toHaveAttribute("href", "/api/exports/5/file");
    expect(screen.getByText("5.0 MB")).toBeInTheDocument();
  });
});
