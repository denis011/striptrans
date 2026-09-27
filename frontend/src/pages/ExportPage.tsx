import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
  type ExportSettings,
  createExport,
  deleteExport,
  exportCheck,
  exportFileUrl,
  finishExport,
  getJob,
  getProject,
  listExports,
  listFonts,
  projectTitle,
} from "../api";
import { type ExportProgress, runExport } from "../export/runExport";

const FORMATS = { cbz: "CBZ (čitači stripova)", pdf: "PDF", zip: "ZIP sa slikama" } as const;
const DEFAULTS: ExportSettings = { format: "cbz", image_format: "jpeg", quality: 92, skipped: "include" };

const megabytes = (size: number | null) => (size ? `${(size / 1024 / 1024).toFixed(1)} MB` : "");

export default function ExportPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => getProject(projectId) });
  const check = useQuery({ queryKey: ["export-check", projectId], queryFn: () => exportCheck(projectId) });
  const exports = useQuery({ queryKey: ["exports", projectId], queryFn: () => listExports(projectId) });
  const fonts = useQuery({ queryKey: ["fonts"], queryFn: listFonts, staleTime: 60_000 });
  const [settings, setSettings] = useState<ExportSettings>(DEFAULTS);
  const [progress, setProgress] = useState<ExportProgress | null>(null);
  const [stage, setStage] = useState<"idle" | "drawing" | "packing">("idle");
  const [packed, setPacked] = useState<{ done: number; total: number } | null>(null); // napredak pakovanja
  const cancelRef = useRef(false);

  const run = useMutation({
    mutationFn: async () => {
      if (!project.data || !fonts.data) throw new Error("podaci se još učitavaju");
      cancelRef.current = false;
      setStage("drawing");
      const created = await createExport(projectId, settings);
      queryClient.invalidateQueries({ queryKey: ["exports", projectId] });
      const result = await runExport({
        exportJob: created,
        pages: project.data.pages.filter((page) => page.kind === "original"),
        series: project.data.series,
        fonts: fonts.data,
        onProgress: setProgress,
        cancelled: () => cancelRef.current,
      });
      setStage("packing");
      let job = await finishExport(created.id);
      setPacked(null);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        job = await getJob(job.id);
        if (job.total) setPacked({ done: job.progress, total: job.total });
      }
      if (job.status !== "done") throw new Error(job.error ?? "pakovanje nije uspelo");
      return result;
    },
    onSettled: () => {
      setStage("idle");
      queryClient.invalidateQueries({ queryKey: ["exports", projectId] });
    },
  });
  const remove = useMutation({
    mutationFn: deleteExport,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exports", projectId] }),
  });

  if (project.isPending) return <main className="container">Učitavanje…</main>;
  if (project.isError) return <main className="container error">{project.error.message}</main>;
  const pages = check.data ?? [];
  const issues = pages.filter((page) => !page.skip && (page.untranslated > 0 || (page.blocks > 0 && !page.cleaned) || !page.reviewed));
  const set = (changes: Partial<ExportSettings>) => setSettings((current) => ({ ...current, ...changes }));

  return (
    <main className="container">
      <p>
        <Link to={`/projects/${projectId}`}>← {projectTitle(project.data)}</Link>
      </p>
      <h1>Izvoz albuma</h1>

      <section className="card">
        <h2>Spremnost</h2>
        {check.isPending ? (
          <p className="detail">Proveravam…</p>
        ) : (
          <>
            <p>
              Stranica: {pages.length} · preskočenih: {pages.filter((page) => page.skip).length} · neočišćenih:{" "}
              {pages.filter((page) => !page.skip && page.blocks > 0 && !page.cleaned).length} · blokova bez prevoda:{" "}
              {pages.reduce((sum, page) => sum + (page.skip ? 0 : page.untranslated), 0)} · nelektorisanih:{" "}
              {pages.filter((page) => !page.skip && !page.reviewed).length}
            </p>
            {issues.length > 0 && (
              <details>
                <summary>Stranice koje nisu gotove ({issues.length}) — izvoz je ipak moguć</summary>
                <ul className="issues">
                  {issues.map((page) => (
                    <li key={page.page_id}>
                      <Link to={`/projects/${projectId}/pages/${page.position}`}>str. {page.position}</Link>:{" "}
                      {[
                        page.blocks > 0 && !page.cleaned && "nije očišćena",
                        page.untranslated > 0 && `${page.untranslated} bez prevoda`,
                        !page.reviewed && "nije lektorisana",
                      ]
                        .filter(Boolean)
                        .join(", ")}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2>Podešavanja</h2>
        <div className="export-form">
          <label>
            Format
            <select aria-label="Format albuma" value={settings.format} onChange={(event) => set({ format: event.target.value as ExportSettings["format"] })}>
              {Object.entries(FORMATS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Slike
            <select aria-label="Format slika" value={settings.image_format} onChange={(event) => set({ image_format: event.target.value as ExportSettings["image_format"] })}>
              <option value="jpeg">JPG</option>
              <option value="png">PNG (bez gubitaka, veći fajl)</option>
            </select>
          </label>
          {settings.image_format === "jpeg" && (
            <label>
              Kvalitet JPG-a
              <input aria-label="Kvalitet JPG-a" type="number" min={50} max={100} value={settings.quality} onChange={(event) => set({ quality: Number(event.target.value) })} />
            </label>
          )}
          <label>
            Preskočene stranice
            <select aria-label="Preskočene stranice" value={settings.skipped} onChange={(event) => set({ skipped: event.target.value as ExportSettings["skipped"] })}>
              <option value="include">uključi neizmenjene (naslovna, reklame)</option>
              <option value="omit">izostavi</option>
            </select>
          </label>
          <label>
            Od strane
            <input aria-label="Od strane" type="number" min={1} value={settings.first ?? ""} placeholder="prve" onChange={(event) => set({ first: event.target.value ? Number(event.target.value) : null })} />
          </label>
          <label>
            Do strane
            <input aria-label="Do strane" type="number" min={1} value={settings.last ?? ""} placeholder="poslednje" onChange={(event) => set({ last: event.target.value ? Number(event.target.value) : null })} />
          </label>
        </div>
        <div className="toolbar-group">
          <button type="button" disabled={run.isPending || !fonts.data} onClick={() => run.mutate()}>
            Izvezi album
          </button>
          {stage === "drawing" && (
            <>
              <progress max={progress?.total ?? 1} value={progress?.done ?? 0} />
              <span data-testid="export-progress">
                Crtam stranice: {progress?.done ?? 0} / {progress?.total ?? "…"}
              </span>
              <button type="button" onClick={() => (cancelRef.current = true)}>
                Prekini
              </button>
            </>
          )}
          {stage === "packing" && (
            <>
              <progress max={packed?.total || 1} value={packed?.done ?? 0} />
              <span data-testid="export-packing">
                Pakujem album{packed ? `: ${packed.done} / ${packed.total}` : "…"}
              </span>
            </>
          )}
          {run.isError && <span className="error">{run.error.message}</span>}
          {run.isSuccess && (
            <span className="detail">
              Gotovo.
              {run.data.overflow.length > 0 && ` Tekst ne staje na stranicama: ${run.data.overflow.join(", ")} — proveri ih.`}
            </span>
          )}
        </div>
      </section>

      <section className="card">
        <h2>Izvezeni albumi</h2>
        {(exports.data ?? []).length === 0 ? (
          <p className="detail">Još nema izvoza.</p>
        ) : (
          <table className="exports">
            <tbody>
              {(exports.data ?? []).map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.created_at + "Z").toLocaleString("sr-Latn")}</td>
                  <td>{item.format.toUpperCase()}</td>
                  <td>{item.positions.length} str.</td>
                  <td>{megabytes(item.size)}</td>
                  <td>
                    {item.status === "done" ? (
                      <a href={exportFileUrl(item.id)} download>
                        Preuzmi
                      </a>
                    ) : item.status === "failed" ? (
                      <span className="error" title={item.error ?? ""}>
                        neuspelo
                      </span>
                    ) : (
                      <span className="detail">{item.status === "packing" ? "pakovanje…" : "u toku…"}</span>
                    )}
                  </td>
                  <td>
                    <button type="button" className="icon" aria-label={`Obriši izvoz ${item.id}`} onClick={() => remove.mutate(item.id)}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
