import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { project, ramon } from "../test/fixtures";
import { mockFetch, renderRoute } from "../test/utils";
import ProjectsPage from "./ProjectsPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProjectsPage", () => {
  it("prikazuje listu projekata", async () => {
    mockFetch({ "/api/series": [ramon], "/api/projects": [project] });
    renderRoute("/", "/", <ProjectsPage />);

    expect(await screen.findByText("Ramon 12 — Pasakr")).toBeInTheDocument();
    expect(screen.getByText("3 stranica · referenca 1")).toBeInTheDocument();
  });

  it("pravi projekat, šalje fajlove i otvara projekat", async () => {
    const fetchMock = mockFetch({
      "/api/series": [ramon],
      "GET /api/projects": [],
      "POST /api/projects": { ...project, pages: [], jobs: [] },
      "POST /api/projects/1/imports": { id: 5, status: "queued" },
    });
    renderRoute("/", "/", <ProjectsPage />);
    await screen.findByRole("option", { name: "Ramon" });

    await userEvent.type(screen.getByLabelText("Broj"), "12");
    const [originalInput, referenceInput] = screen.getAllByTestId("file-input");
    await userEvent.upload(originalInput, new File(["it"], "ramon-ita.cbr"));
    await userEvent.upload(referenceInput, new File(["sr"], "ramon-srp.cbr"));
    await userEvent.click(screen.getByRole("button", { name: "Napravi projekat" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/projects/1"));
    const create = fetchMock.mock.calls.find(([, init]) => init?.method === "POST" && !String(init.body).startsWith("[object"));
    expect(JSON.parse(String(create?.[1]?.body))).toMatchObject({ series_id: 1, issue_number: "12" });
    const imports = fetchMock.mock.calls.filter(([url]) => url === "/api/projects/1/imports");
    const kinds = imports.map(([, init]) => (init?.body as FormData).get("kind"));
    expect(kinds).toEqual(["original", "reference"]);
  });
});
