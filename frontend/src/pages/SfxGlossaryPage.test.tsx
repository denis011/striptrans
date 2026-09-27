import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockFetch, renderRoute } from "../test/utils";
import SfxGlossaryPage from "./SfxGlossaryPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSfx() {
  const fetchMock = mockFetch({
    "GET /api/sfx-glossary": [{ id: 1, source: "SWACK", target: "SCVAK", note: null }],
    "GET /api/sfx-glossary/missing": [{ source: "SPLASH", suggestion: "SPLAŠ", count: 3 }],
    "POST /api/sfx-glossary": { id: 2, source: "SPLASH", target: "SPLAŠ!", note: null },
  });
  renderRoute("/sfx-glossary", "/sfx-glossary", <SfxGlossaryPage />);
  return fetchMock;
}

describe("SfxGlossaryPage", () => {
  it("prikazuje glosar i dodaje reč koje nema, sa ispravljenim predlogom", async () => {
    const fetchMock = renderSfx();

    expect(await screen.findByDisplayValue("SCVAK")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("tab", { name: "Nisu u glosaru (1)" }));
    const target = screen.getByRole("textbox", { name: "Prevod: SPLASH" });
    expect(target).toHaveValue("SPLAŠ");
    await userEvent.type(target, "!");
    await userEvent.click(screen.getByRole("button", { name: "Dodaj SPLASH" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => url === "/api/sfx-glossary" && init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ source: "SPLASH", target: "SPLAŠ!" });
    });
  });
});
