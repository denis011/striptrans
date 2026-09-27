import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { vi } from "vitest";

/** Mock za fetch: ključ je "METOD /putanja" ili samo "/putanja" (bilo koji metod). */
export function mockFetch(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url}` in routes ? `${method} ${url}` : url;
    if (!(key in routes)) {
      return Response.json({ detail: `nema mock-a za ${method} ${url}` }, { status: 404 });
    }
    return Response.json(routes[key]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function LocationProbe() {
  return <p data-testid="location">{useLocation().pathname}</p>;
}

/** Renderuje element na ruti `path`; sve ostale rute prikazuju trenutnu putanju. */
export function renderRoute(path: string, url: string, element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
