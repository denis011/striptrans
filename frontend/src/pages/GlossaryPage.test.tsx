import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { glossaryEntry, job, project, ramon } from "../test/fixtures";
import { mockFetch, renderRoute } from "../test/utils";
import GlossaryPage from "./GlossaryPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

const approved = glossaryEntry({ id: 1 });
const suggested = glossaryEntry({ id: 2, source: "GREYWOOD", target: "GREJVUD", kind: "place", status: "suggested", origin: "reference", occurrences: 7 });

function renderGlossary(extra: Record<string, unknown> = {}) {
  const fetchMock = mockFetch({
    "/api/series": [ramon],
    "/api/projects": [project, { ...project, id: 3, translated_title: "Pasakr (referenca)" }],
    "GET /api/series/1/glossary": [approved, suggested],
    ...extra,
  });
  renderRoute("/series/:seriesId/glossary", "/series/1/glossary", <GlossaryPage />);
  return fetchMock;
}

function body(fetchMock: ReturnType<typeof mockFetch>, method: string, url: string) {
  const call = fetchMock.mock.calls.find(([callUrl, init]) => callUrl === url && init?.method === method);
  return call && JSON.parse(String(call[1]?.body));
}

describe("GlossaryPage", () => {
  it("prikazuje odobrene stavke i predloge", async () => {
    renderGlossary();

    expect(await screen.findByRole("heading", { name: "Glosar — Ramon" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("MIĆO")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("GREJVUD")).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: "Predlozi (1)" }));
    expect(screen.getByDisplayValue("GREJVUD")).toBeInTheDocument();
    expect(screen.getByText("7×")).toBeInTheDocument();
  });

  it("dodaje novu stavku", async () => {
    const fetchMock = renderGlossary({ "POST /api/series/1/glossary": approved });
    await screen.findByDisplayValue("MIĆO");

    await userEvent.type(screen.getByLabelText("Italijanski"), "Spirito con la scure");
    await userEvent.type(screen.getByLabelText("Srpski"), "Duh sa sekirom");
    await userEvent.selectOptions(screen.getByLabelText("Vrsta"), "phrase");
    await userEvent.click(screen.getByRole("button", { name: "Dodaj" }));

    await waitFor(() => expect(body(fetchMock, "POST", "/api/series/1/glossary")).toBeTruthy());
    expect(body(fetchMock, "POST", "/api/series/1/glossary")).toEqual({
      source: "Spirito con la scure",
      target: "Duh sa sekirom",
      kind: "phrase",
    });
  });

  it("odobrava predlog", async () => {
    const fetchMock = renderGlossary({ "PATCH /api/glossary/2": { ...suggested, status: "approved" } });
    await userEvent.click(await screen.findByRole("tab", { name: "Predlozi (1)" }));

    await userEvent.click(screen.getByRole("button", { name: "Odobri" }));

    await waitFor(() => expect(body(fetchMock, "PATCH", "/api/glossary/2")).toEqual({ status: "approved" }));
  });

  it("čuva izmenjen prevod kad polje izgubi fokus", async () => {
    const fetchMock = renderGlossary({ "PATCH /api/glossary/1": approved });
    const input = await screen.findByLabelText("Srpski: MICO");

    await userEvent.clear(input);
    await userEvent.type(input, "MIĆO!");
    await userEvent.tab();

    await waitFor(() => expect(body(fetchMock, "PATCH", "/api/glossary/1")).toEqual({ target: "MIĆO!" }));
  });

  it("pokreće predloge iz objavljenog prevoda", async () => {
    const fetchMock = renderGlossary({
      "POST /api/series/1/glossary/suggest": job({ id: 9, type: "glossary_suggest" }),
      "GET /api/jobs/9": job({ id: 9, type: "glossary_suggest", status: "done" }),
    });
    // isti projekti su ponuđeni u oba izbora
    await screen.findAllByRole("option", { name: "Ramon 12 — Pasakr (referenca)" });

    await userEvent.selectOptions(screen.getByLabelText("Original"), "1");
    await userEvent.selectOptions(screen.getByLabelText("Objavljeni prevod"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Predloži stavke" }));

    expect(await screen.findByText("Predlozi za glosar: završeno")).toBeInTheDocument();
    expect(body(fetchMock, "POST", "/api/series/1/glossary/suggest")).toEqual({ project_id: 1, reference_project_id: 3 });
  });

  it("čuva uputstvo za prevod serijala", async () => {
    const fetchMock = renderGlossary({ "PATCH /api/series/1": { ...ramon, translation_notes: "Glavni lik je odmeren." } });
    const notes = await screen.findByLabelText("Uputstvo za prevod serijala");

    await userEvent.type(notes, "Glavni lik je odmeren.");
    await userEvent.click(screen.getByRole("button", { name: "Sačuvaj uputstvo" }));

    await waitFor(() => expect(body(fetchMock, "PATCH", "/api/series/1")).toEqual({ translation_notes: "Glavni lik je odmeren." }));
  });
});
