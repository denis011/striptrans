import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import JobQueue, { formatDuration, jobDuration } from "./JobQueue";

const job = (id: number, status: string, progress = 0, total = 0) => ({
  id,
  type: "process_project",
  status,
  project_id: id,
  progress,
  total,
  cancel_requested: false,
  error: null,
  result: null,
  created_at: "2026-09-24T18:00:00",
  updated_at: "2026-09-24T18:00:00",
  project_title: `Ramon — ${670 + id}`,
});

afterEach(() => vi.unstubAllGlobals());

describe("JobQueue", () => {
  it("procenjuje trajanje tek posle minut rada", () => {
    expect(jobDuration({ at: 0, progress: 10 }, { at: 30_000, progress: 12 }, 100)).toBeNull();
    // 10 strana za 5 min → 100 strana za 50 min
    expect(jobDuration({ at: 0, progress: 10 }, { at: 300_000, progress: 20 }, 100)).toBe(3_000_000);
    expect(formatDuration(3_000_000)).toBe("50 min");
    expect(formatDuration(20_400_000)).toBe("5 h 40 min");
  });

  it("prikazuje posao koji radi i poslove koji čekaju, redom", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json([job(4, "running", 40, 100), job(5, "queued"), job(6, "queued")])),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <JobQueue />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Radi: 1 · čeka: 2")).toBeInTheDocument();
    expect(screen.getByText("Ramon — 674")).toBeInTheDocument();
    expect(screen.getByText("Obrada: 40 / 100")).toBeInTheDocument();
    expect(screen.getAllByText("Obrada čeka na red…")).toHaveLength(2);
  });

  it("crtanje albuma (u tabu za izvoz) je u redu, ali bez dugmeta Prekini", async () => {
    const draw = { ...job(-3, "running", 34, 98), type: "export_draw", result: { stage: "čeka otvoren tab za izvoz" } };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json([draw])));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <JobQueue />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Crtanje albuma (čeka otvoren tab za izvoz): 34 / 98")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prekini" })).not.toBeInTheDocument();
  });
});
