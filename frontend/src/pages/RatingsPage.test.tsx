import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RatingStudy } from "../api";
import { mockFetch, renderRoute } from "../test/utils";
import RatingsPage from "./RatingsPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function study(scores: (number | null)[]): RatingStudy {
  return {
    study: "faza3",
    total_items: 1,
    rated_items: scores.every((s) => s !== null) ? 1 : 0,
    items: [
      {
        item: 1,
        page_position: 10,
        block_position: 2,
        source: "SEGUITEMI!",
        candidates: [
          { id: 7, order: 1, translation: "SLEDITE ME!", score: scores[0] },
          { id: 6, order: 0, translation: "PRATITE ME!", score: scores[1] },
        ],
      },
    ],
  };
}

describe("RatingsPage", () => {
  it("prikazuje blok i kandidate bez imena modela, i čuva ocenu", async () => {
    const fetchMock = mockFetch({
      "GET /api/ratings/faza3": study([null, null]),
      "PUT /api/ratings/faza3/6": { id: 6, order: 0, translation: "PRATITE ME!", score: 5 },
    });
    renderRoute("/ratings/:study", "/ratings/faza3", <RatingsPage />);

    expect(await screen.findByText("SEGUITEMI!")).toBeInTheDocument();
    expect(screen.getByTestId("rating-progress")).toHaveTextContent("Ocenjeno 0 / 1");
    const [first, second] = screen.getAllByText(/ME!$/);
    expect([first.textContent, second.textContent]).toEqual(["PRATITE ME!", "SLEDITE ME!"]);

    await userEvent.click(screen.getByRole("button", { name: "Prevod A: ocena 5" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Prevod A: ocena 5" })).toHaveClass("active"));
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/ratings/faza3/6");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ score: 5 });
    expect(screen.queryByText("Rezultat")).toBeNull();
  });

  it("posle poslednje ocene prikazuje rezultat po modelu", async () => {
    mockFetch({
      "GET /api/ratings/faza3": study([3, 5]),
      "GET /api/ratings/faza3/summary": {
        study: "faza3",
        candidates: [{ candidate: "gemma3:12b/glossary", average: 5, good_share: 1, count: 1 }],
      },
    });
    renderRoute("/ratings/:study", "/ratings/faza3", <RatingsPage />);

    expect(await screen.findByText("gemma3:12b/glossary")).toBeInTheDocument();
    expect(screen.getByText("100 %")).toBeInTheDocument();
  });
});
