import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  type PageKind,
  type ProjectProgress,
  cancelJob,
  cleanProject,
  reshapeProject,
  prepareProject,
  deletePage,
  deleteProject,
  getProject,
  importPages,
  listOcrModels,
  listTranslationModels,
  pageThumbnailUrl,
  processProject,
  projectScriptUrl,
  translateProject,
  projectTitle,
  reorderPages,
  resetPageOrder,
  updatePage,
} from "../api";
import FileDrop from "../components/FileDrop";
import JobStatus, { isActiveJob } from "../components/JobStatus";
import { loadSetting } from "../storage";
import { importRanks, isReordered } from "../pageOrder";
import { moveItem } from "../viewer/navigation";

export default function ProjectPage() {
  const projectId = Number(useParams().projectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<PageKind>("original");
  const [dragged, setDragged] = useState<number | null>(null);
  const [replaceBlocks, setReplaceBlocks] = useState(false);
  const [replaceTranslations, setReplaceTranslations] = useState(false);
  const [chosenModel, setChosenModel] = useState<string | null>(() => loadSetting("striptrans.ocrModel", null));
  const ocrModels = useQuery({ queryKey: ["ocr-models"], queryFn: listOcrModels, staleTime: 60_000 });
  const modelNames = ocrModels.data?.models.map((model) => model.name) ?? [];
  const processModel = [chosenModel, ocrModels.data?.default_model, modelNames[0]].find(
    (name): name is string => !!name && modelNames.includes(name),
  );

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    // posao u redu ili izvoz u toku (crtanje u drugom tabu): stanje se osvežava samo
    refetchInterval: (query) => (query.state.data?.jobs.some(isActiveJob) || query.state.data?.progress.export_active ? 1000 : false),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["project", projectId] });
  const upload = useMutation({
    mutationFn: (files: File[]) => importPages(projectId, kind, files),
    onSuccess: refresh,
  });
  const removePage = useMutation({ mutationFn: deletePage, onSuccess: refresh });
  // preskočena stranica (naslovna, impresum, reklama) ne ulazi u obradu, ali ulazi u album neizmenjena
  const skipPage = useMutation({
    mutationFn: ({ id, skip }: { id: number; skip: boolean }) => updatePage(id, { skip }),
    onSuccess: refresh,
  });
  const reorder = useMutation({
    mutationFn: (ids: number[]) => reorderPages(projectId, kind, ids),
    onSuccess: refresh,
  });
  const resetOrder = useMutation({ mutationFn: () => resetPageOrder(projectId), onSuccess: refresh });
  const processAll = useMutation({
    mutationFn: () => processProject(projectId, processModel, replaceBlocks),
    onSuccess: refresh,
  });
  const cancel = useMutation({ mutationFn: cancelJob, onSuccess: refresh });
  const translationModels = useQuery({ queryKey: ["translation-models"], queryFn: listTranslationModels, staleTime: 60_000 });
  const translationNames = translationModels.data?.models.map((model) => model.name) ?? [];
  const [chosenTranslationModel, setChosenTranslationModel] = useState<string | null>(() => loadSetting("striptrans.translationModel", null));
  const translationModel = [chosenTranslationModel, translationModels.data?.default_model, translationNames[0]].find(
    (name): name is string => !!name && translationNames.includes(name),
  );
  const translateAll = useMutation({
    mutationFn: () => translateProject(projectId, translationModel, replaceTranslations),
    onSuccess: refresh,
  });
  const cleanAll = useMutation({ mutationFn: () => cleanProject(projectId), onSuccess: refresh });
  const reshape = useMutation({ mutationFn: () => reshapeProject(projectId), onSuccess: refresh });
  const prepareAll = useMutation({ mutationFn: () => prepareProject(projectId, processModel, translationModel), onSuccess: refresh });
  const removeProject = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
  });

  if (project.isPending) return <main className="container">Učitavanje…</main>;
  if (project.isError) {
    return (
      <main className="container">
        <p className="error">{project.error.message}</p>
      </main>
    );
  }

  const data = project.data;
  const progress = data.progress;
  const untranslated = progress.translation.none ?? 0;
  const busy = data.jobs.some(isActiveJob);
  // album je menjan posle poslednjeg izvoza: izvoz treba ponoviti
  const stale = !!progress.exported_at && !!progress.changed_at && progress.changed_at > progress.exported_at;
  const pages = data.pages.filter((page) => page.kind === kind);
  const lastJob = data.jobs[0];
  const reordered = {
    original: isReordered(data.pages.filter((page) => page.kind === "original")),
    reference: isReordered(data.pages.filter((page) => page.kind === "reference")),
  };
  const ranks = importRanks(pages);

  const dropOn = (targetId: number) => {
    if (dragged === null) return;
    const ids = pages.map((page) => page.id);
    const reordered = moveItem(ids, dragged, targetId);
    if (reordered !== ids) reorder.mutate(reordered);
  };

  return (
    <main className="container wide">
      <div className="page-header">
        <div>
          <h1>{projectTitle(data)}</h1>
          <span className="detail">
            {data.page_count} stranica · referenca {data.reference_page_count}
          </span>
        </div>
        <div className="actions">
          {data.page_count > 0 && (
            <Link className="button" to={`/projects/${projectId}/pages/1`}>
              Otvori pregled
            </Link>
          )}
          <button
            type="button"
            className="danger"
            onClick={() => window.confirm("Obrisati projekat i sve stranice?") && removeProject.mutate()}
          >
            Obriši projekat
          </button>
        </div>
      </div>

      <div className="shortcut">
        <span>
          <strong>Brzo:</strong> koraci 3, 4 i 6 odjednom — urađeno se preskače, pa se može ponoviti posle ispravki
        </span>
        <button
          type="button"
          disabled={busy || !processModel || !translationModel || data.page_count === 0 || prepareAll.isPending}
          onClick={() => prepareAll.mutate()}
        >
          Pripremi ceo album
        </button>
        {prepareAll.isError && <span className="error">{prepareAll.error.message}</span>}
      </div>

      <ol className="steps" aria-label="Koraci obrade">
        <Step number={1} title="Uvezi stranice" done={data.page_count > 0}
          status={`${data.page_count} originala · ${data.reference_page_count} reference`}>
          <span className="detail">Prevuci CBZ, CBR, PDF ili slike u polje iznad sličica.</span>
        </Step>
        <Step number={2} title="Označi stranice koje se preskaču" done={progress.skipped.length > 0}
          status={progress.skipped.length ? `preskočeno: ${progress.skipped.join(", ")}` : "nijedna"}>
          <span className="detail">Naslovna, impresum, reklame — dugme ⊘ na sličici. U album ulaze neizmenjene.</span>
        </Step>
        <Step number={3} title="Pronađi blokove i pročitaj tekst (OCR)"
          done={progress.pages > 0 && progress.with_blocks >= progress.pages}
          status={`${progress.with_blocks} od ${progress.pages} stranica${progress.unread ? ` · ${progress.unread} nepročitanih blokova — pokreni obradu projekta` : ""}`}>
          <select aria-label="OCR model za obradu" value={processModel ?? ""} onChange={(event) => setChosenModel(event.target.value)}>
            {modelNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <label>
            <input type="checkbox" checked={replaceBlocks} onChange={(event) => setReplaceBlocks(event.target.checked)} /> Zameni
            postojeće blokove
          </label>
          <button
            type="button"
            disabled={busy || !processModel || data.page_count === 0 || processAll.isPending}
            onClick={() => processAll.mutate()}
          >
            Obradi ceo projekat
          </button>
          {processAll.isError && <span className="error">{processAll.error.message}</span>}
        </Step>
        <Step number={4} title="Prevedi" done={progress.blocks > 0 && !untranslated}
          status={translationStatus(progress)}>
          <select aria-label="Model prevoda" value={translationModel ?? ""} onChange={(event) => setChosenTranslationModel(event.target.value)}>
            {translationNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <label>
            <input type="checkbox" checked={replaceTranslations} onChange={(event) => setReplaceTranslations(event.target.checked)} /> Ponovo
            prevedi nacrte
          </label>
          <button
            type="button"
            disabled={busy || !translationModel || data.page_count === 0 || translateAll.isPending}
            onClick={() => translateAll.mutate()}
          >
            Prevedi ceo projekat
          </button>
          {translateAll.isError && <span className="error">{translateAll.error.message}</span>}
        </Step>
        <Step number={5} title="Lektura" done={progress.pages > 0 && progress.proofread >= progress.pages}
          status={`${progress.proofread} od ${progress.pages} stranica lektorisano`}>
          <a
            className="button"
            href={projectScriptUrl(projectId, "html")}
            target="_blank"
            rel="noreferrer"
            title="Tabela original/prevod po oblačiću, za čitanje i lekturu van aplikacije"
          >
            Scenario
          </a>
          <a className="button" href={projectScriptUrl(projectId, "csv")} download title="Isti scenario kao tabela (Excel, LibreOffice)">
            CSV
          </a>
          <Link className="button" to={`/series/${data.series.id}/glossary`}>
            Glosar
          </Link>
          <span className="detail">U editoru: Ctrl+Enter odobrava blok, Ctrl+Shift+Enter celu stranicu.</span>
        </Step>
        <Step number={6} title="Očisti originalni tekst" done={progress.pages > 0 && progress.cleaned >= progress.pages}
          status={`${progress.cleaned} od ${progress.pages} stranica`}>
          <button type="button" disabled={busy || data.page_count === 0 || cleanAll.isPending} onClick={() => cleanAll.mutate()}>
            Očisti ceo projekat
          </button>
          <span className="detail">Oblačići se brišu bojom papira; onomatopeje i natpisi preko crteža samo ako imaju drugačiji prevod.</span>
          {cleanAll.isError && <span className="error">{cleanAll.error.message}</span>}
        </Step>
        <Step
          number={7}
          title="Doteraj slaganje u editoru"
          status={`tekst koji ne staje je crven; panel kaže koji red i koliko${progress.ai_calls ? ` · AI prepravke: ${progress.ai_calls} (${(progress.ai_cost ?? 0).toFixed(2)} $)` : ""}`}
        >
          {data.page_count > 0 && (
            <Link className="button" to={`/projects/${projectId}/pages/1`}>
              Otvori pregled
            </Link>
          )}
          <button
            type="button"
            disabled={busy || progress.cleaned === 0 || reshape.isPending}
            onClick={() => reshape.mutate()}
            title={'Kad tekst „ne staje" iako je oblačić dovoljno velik'}
          >
            Ponovo izmeri oblačiće
          </button>
          <span className="detail">Oblik oblačića se meri pri čišćenju; ovim se osvežava iz očišćenih strana, bez ponovnog čišćenja.</span>
          {reshape.isError && <span className="error">{reshape.error.message}</span>}
        </Step>
        <Step number={8} title="Izvezi album" done={!!progress.exported_at && !stale}
          status={exportStatus(progress, stale)}>
          <Link className="button" to={`/projects/${projectId}/export`}>
            Izvoz albuma
          </Link>
          {progress.export_active && <ExportProgressBar active={progress.export_active} />}
        </Step>
      </ol>
      {data.jobs.filter(isActiveJob).map((job) => (
        <JobStatus key={job.id} job={job} onCancel={(id) => cancel.mutate(id)} />
      ))}
      {lastJob && !isActiveJob(lastJob) && lastJob.status !== "done" && <JobStatus job={lastJob} />}
      {(reordered.original || reordered.reference) && (
        <div className="notice" data-testid="order-notice">
          <span>
            Raspored stranica je izmenjen:{" "}
            {[reordered.original && "original", reordered.reference && "referenca"].filter(Boolean).join(", ")}
          </span>
          <button
            type="button"
            disabled={resetOrder.isPending}
            onClick={() => window.confirm("Vratiti original i referencu u izvorni redosled?") && resetOrder.mutate()}
          >
            Vrati izvorni redosled
          </button>
        </div>
      )}

      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={kind === "original"} onClick={() => setKind("original")}>
          Original ({data.page_count}){reordered.original && " •"}
        </button>
        <button type="button" role="tab" aria-selected={kind === "reference"} onClick={() => setKind("reference")}>
          Referenca ({data.reference_page_count}){reordered.reference && " •"}
        </button>
      </div>

      <FileDrop
        onFiles={(files) => upload.mutate(files)}
        disabled={upload.isPending}
        label={kind === "original" ? "Dodaj stranice originala" : "Dodaj stranice referentnog izdanja"}
      />
      {upload.isError && <p className="error">{upload.error.message}</p>}

      <ul className="page-grid">
        {pages.map((page) => (
          <li
            key={page.id}
            draggable
            className={[dragged === page.id && "dragging", ranks.get(page.id) !== page.position && "moved", page.skip && "skipped"]
              .filter(Boolean)
              .join(" ")}
            onDragStart={() => setDragged(page.id)}
            onDragEnd={() => setDragged(null)}
            onDragOver={(event) => dragged !== null && event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              dropOn(page.id);
              setDragged(null);
            }}
          >
            <Link to={`/projects/${projectId}/pages/${page.position}`} draggable={false}>
              <img
                src={pageThumbnailUrl(page.id)}
                alt={`Stranica ${page.position}`}
                title={page.source_name}
                loading="lazy"
                draggable={false}
              />
            </Link>
            <div className="page-meta">
              <span>
                {page.position}
                {ranks.get(page.id) !== page.position && (
                  <span className="moved-from" title="Izvorna pozicija"> (izv. {ranks.get(page.id)})</span>
                )}
              </span>
              {page.ocr_reviewed && <span className="badge ok">pregledana</span>}
              <button
                type="button"
                className={`icon skip${page.skip ? " on" : ""}`}
                aria-label={`Preskoči stranicu ${page.position}`}
                aria-pressed={page.skip}
                title={
                  page.skip
                    ? "Stranica se ne obrađuje; u album ulazi neizmenjena"
                    : "Preskoči stranicu (naslovna, impresum, reklama)"
                }
                disabled={skipPage.isPending}
                onClick={() => skipPage.mutate({ id: page.id, skip: !page.skip })}
              >
                ⊘
              </button>
              <button
                type="button"
                className="icon"
                aria-label={`Obriši stranicu ${page.position}`}
                onClick={() =>
                  window.confirm(`Obrisati stranicu ${page.position}?`) && removePage.mutate(page.id)
                }
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}

/** Stanje prevoda u jednom redu: koliko čeka, koliko je nacrta, izmenjeno i odobreno. */
function translationStatus(progress: ProjectProgress): string {
  const { none = 0, draft = 0, edited = 0, approved = 0 } = progress.translation;
  if (progress.blocks === 0) return "nema blokova sa tekstom";
  const parts = [none && `${none} bez prevoda`, draft && `${draft} nacrta`, edited && `${edited} izmenjeno`, approved && `${approved} odobreno`];
  return parts.filter(Boolean).join(" · ");
}

function exportStatus(progress: ProjectProgress, stale: boolean): string {
  if (!progress.exported_at) return "još nije izvezen";
  const when = new Date(progress.exported_at).toLocaleString("sr-Latn");
  return stale ? `poslednji izvoz ${when} — album je menjan posle toga` : `poslednji izvoz ${when}`;
}

function Step({ number, title, status, done = false, children }: { number: number; title: string; status: string; done?: boolean; children?: ReactNode }) {
  return (
    <li className={`step${done ? " done" : ""}`}>
      <span className="step-number" aria-hidden>
        {done ? "✓" : number}
      </span>
      <div className="step-body">
        <div className="step-head">
          <strong>
            {number}. {title}
          </strong>
          <span className="step-status">{status}</span>
        </div>
        {children && <div className="step-actions">{children}</div>}
      </div>
    </li>
  );
}

/** Izvoz u toku (korak 8): crtanje stranica u tabu „Izvoz albuma", pa pakovanje na serveru. */
function ExportProgressBar({ active }: { active: NonNullable<ProjectProgress["export_active"]> }) {
  if (active.stage === "packing") {
    return (
      <span className="job" data-testid="export-active">
        <span>Pakujem album…</span>
        <progress />
      </span>
    );
  }
  return (
    <span className="job" data-testid="export-active">
      <span>
        Crtam stranice: {active.done} / {active.total}
        {active.stale && " — čeka otvoren tab za izvoz"}
      </span>
      <progress max={active.total || 1} value={active.done} />
    </span>
  );
}
