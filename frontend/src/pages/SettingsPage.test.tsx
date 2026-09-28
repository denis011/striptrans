import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockFetch, renderRoute } from "../test/utils";
import SettingsPage from "./SettingsPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

const builtin = { id: 1, name: "Podrazumevani", text: "- ŽIVO.", builtin: true, active: true, changed: false };
const modern = { id: 2, name: "Moderni", text: "- SLENG.", builtin: false, active: false, changed: false };

function calls(fetchMock: ReturnType<typeof mockFetch>, method: string, url: string) {
  return fetchMock.mock.calls.filter(([callUrl, init]) => callUrl === url && (init?.method ?? "GET") === method);
}

function renderSettings() {
  const fetchMock = mockFetch({
    "GET /api/translation-styles": [builtin, modern],
    "PATCH /api/translation-styles/1": { ...builtin, text: "- KRATKO.", changed: true },
    "POST /api/translation-styles/2/activate": { ...modern, active: true },
    "POST /api/translation-styles": { ...modern, id: 3, name: "Klasični", text: "- ŽIVO." },
  });
  renderRoute("/settings", "/settings", <SettingsPage />);
  return fetchMock;
}

describe("SettingsPage", () => {
  it("prikazuje aktivni stil i čuva izmenu teksta", async () => {
    const fetchMock = renderSettings();
    const text = await screen.findByLabelText("Uputstvo za stil prevoda");
    expect(text).toHaveValue("- ŽIVO.");
    expect(screen.getByLabelText("Ime stila")).toBeDisabled(); // ugrađeni stil zadržava ime
    expect(screen.getByRole("button", { name: "Vrati podrazumevano" })).toBeDisabled();

    await userEvent.clear(text);
    await userEvent.type(text, "- KRATKO.");
    await userEvent.click(screen.getByRole("button", { name: "Sačuvaj" }));

    await waitFor(() => expect(calls(fetchMock, "PATCH", "/api/translation-styles/1")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "PATCH", "/api/translation-styles/1")[0][1]?.body))).toEqual({ name: "Podrazumevani", text: "- KRATKO." });
  });

  it("bira drugi stil, aktivira ga i pravi nov stil kao kopiju izabranog", async () => {
    const fetchMock = renderSettings();
    await userEvent.click(await screen.findByRole("button", { name: "Moderni" }));
    expect(screen.getByLabelText("Uputstvo za stil prevoda")).toHaveValue("- SLENG.");
    await userEvent.click(screen.getByRole("button", { name: "Koristi ovaj stil" }));
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/translation-styles/2/activate")).toHaveLength(1));

    await userEvent.type(screen.getByLabelText("Ime novog stila"), "Klasični");
    await userEvent.click(screen.getByRole("button", { name: "Dodaj" }));
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/translation-styles")).toHaveLength(1));
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/translation-styles")[0][1]?.body))).toEqual({ name: "Klasični", text: "- SLENG." });
  });
});
