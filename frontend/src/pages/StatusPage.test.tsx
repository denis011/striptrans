import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import StatusPage from "./StatusPage";
import type { Health } from "../api";

const healthy: Health = {
  status: "ok",
  database: { ok: true },
  worker: { ok: true, last_seen: "2026-09-15T10:00:00+00:00" },
  llama_server: {
    ok: true,
    url: "http://host.docker.internal:8081",
    version: "b11189-abc",
    model: "qwen2.5vl:7b",
    models: [
      {
        name: "qwen2.5vl:7b",
        file: "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        size: null,
        capabilities: ["completion", "vision"],
      },
    ],
  },
};

function mockFetch(handler: (url: string) => Response) {
  // red poslova je prazan, osim ako test kaže drugačije
  vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === "/api/jobs" ? Response.json([]) : handler(url))));
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StatusPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("prikazuje status servisa i instalirane modele", async () => {
    mockFetch(() => Response.json(healthy));
    renderApp();

    expect(await screen.findByText(/b11189-abc/)).toBeInTheDocument();
    expect(screen.getByText("qwen2.5vl:7b")).toBeInTheDocument();
    expect(screen.getByText("Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf")).toBeInTheDocument();
    expect(screen.getByTestId("status-Worker")).toHaveClass("status-ok");
    expect(screen.getByTestId("status-llama-server")).toHaveClass("status-ok");
  });

  it("prikazuje Ollamu kad je ona OCR server", async () => {
    mockFetch(() => Response.json({ ...healthy, llama_server: { ...healthy.llama_server, server: "ollama", version: "Ollama 0.34.4" } }));
    renderApp();

    expect(await screen.findByText(/Ollama 0\.34\.4/)).toBeInTheDocument();
    expect(screen.getByTestId("status-Ollama")).toHaveClass("status-ok");
  });

  it("označava API kao nedostupan kad backend ne odgovara", async () => {
    mockFetch(() => new Response("", { status: 502, statusText: "Bad Gateway" }));
    renderApp();

    await waitFor(() => expect(screen.getByTestId("status-API")).toHaveClass("status-error"));
    expect(screen.getByText("502 Bad Gateway")).toBeInTheDocument();
  });

  it("pokreće LLM test i prikazuje brzinu generisanja", async () => {
    mockFetch((url) =>
      url === "/api/debug/llm"
        ? Response.json({
            response: "Nemamo vremena sada.",
            model: "qwen2.5vl:7b",
            load_seconds: 0,
            prompt_tokens_per_second: 158,
            eval_tokens_per_second: 59.2,
          })
        : Response.json(healthy),
    );
    renderApp();

    await userEvent.click(screen.getByRole("button", { name: "Pokreni" }));

    expect(await screen.findByText("Nemamo vremena sada.")).toBeInTheDocument();
    expect(screen.getByText(/generisanje 59\.2 tok\/s/)).toBeInTheDocument();
  });
});
