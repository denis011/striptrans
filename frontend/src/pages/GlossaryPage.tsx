import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import {
  type GlossaryChanges,
  type GlossaryEntry,
  type GlossaryKind,
  createGlossaryEntry,
  deleteGlossaryEntry,
  getJob,
  listGlossary,
  listProjects,
  listSeries,
  projectTitle,
  suggestGlossary,
  updateGlossaryEntry,
} from "../api";
import JobStatus, { isActiveJob } from "../components/JobStatus";

const KINDS: [GlossaryKind, string][] = [
  ["name", "Ime"],
  ["place", "Mesto"],
  ["phrase", "Izraz"],
  ["sfx", "Onomatopeja"],
];

function KindSelect({ value, label, onChange }: { value: GlossaryKind; label: string; onChange: (kind: GlossaryKind) => void }) {
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value as GlossaryKind)}>
      {KINDS.map(([kind, name]) => (
        <option key={kind} value={kind}>
          {name}
        </option>
      ))}
    </select>
  );
}

function GlossaryRow({
  entry,
  onChange,
  onDelete,
}: {
  entry: GlossaryEntry;
  onChange: (changes: GlossaryChanges) => void;
  onDelete: () => void;
}) {
  const [source, setSource] = useState(entry.source);
  const [target, setTarget] = useState(entry.target);
  const [note, setNote] = useState(entry.note ?? "");
  const saveText = (field: "source" | "target", value: string, original: string) => {
    if (value.trim() && value !== original) onChange({ [field]: value });
  };

  return (
    <tr className={entry.status === "suggested" ? "suggested" : ""}>
      <td>
        <input aria-label={`Italijanski: ${entry.source}`} value={source} onChange={(e) => setSource(e.target.value)} onBlur={() => saveText("source", source, entry.source)} />
      </td>
      <td>
        <input aria-label={`Srpski: ${entry.source}`} value={target} onChange={(e) => setTarget(e.target.value)} onBlur={() => saveText("target", target, entry.target)} />
      </td>
      <td>
        <KindSelect label={`Vrsta: ${entry.source}`} value={entry.kind} onChange={(kind) => onChange({ kind })} />
      </td>
      <td>
        <input aria-label={`Napomena: ${entry.source}`} value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => note !== (entry.note ?? "") && onChange({ note })} />
      </td>
      {entry.status === "suggested" && <td className="detail">{entry.occurrences}×</td>}
      <td className="row-actions">
        {entry.status === "suggested" && (
          <button type="button" onClick={() => onChange({ status: "approved" })}>
            Odobri
          </button>
        )}
        <button type="button" className="icon" aria-label={`Obriši ${entry.source}`} onClick={() => window.confirm(`Obrisati „${entry.source}"?`) && onDelete()}>
          ✕
        </button>
      </td>
    </tr>
  );
}

export default function GlossaryPage() {
  const seriesId = Number(useParams().seriesId);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<GlossaryEntry["status"]>("approved");
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState({ source: "", target: "", kind: "name" as GlossaryKind, note: "" });

  const [sourceProject, setSourceProject] = useState(0);
  const [referenceProject, setReferenceProject] = useState(0);
  const [jobId, setJobId] = useState<number | null>(null);
  const series = useQuery({ queryKey: ["series"], queryFn: listSeries });
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId ?? 0),
    enabled: jobId !== null,
    refetchInterval: (query) => (isActiveJob(query.state.data) ? 2000 : false),
  });
  const suggest = useMutation({
    mutationFn: () => suggestGlossary(seriesId, sourceProject, referenceProject),
    onSuccess: (started) => setJobId(started.id),
  });
  const jobStatus = job.data?.status;
  useEffect(() => {
    if (jobStatus === "done") queryClient.invalidateQueries({ queryKey: ["glossary", seriesId] });
  }, [jobStatus, queryClient, seriesId]);
  const entries = useQuery({ queryKey: ["glossary", seriesId], queryFn: () => listGlossary(seriesId) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["glossary", seriesId] });
  const create = useMutation({
    mutationFn: () => createGlossaryEntry(seriesId, { ...draft, note: draft.note || undefined }),
    onSuccess: () => {
      setDraft((current) => ({ ...current, source: "", target: "", note: "" }));
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: GlossaryChanges }) => updateGlossaryEntry(id, changes),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: deleteGlossaryEntry, onSuccess: refresh });
  const error = [create, update, remove, suggest].find((mutation) => mutation.error)?.error;

  const all = entries.data ?? [];
  const count = (status: GlossaryEntry["status"]) => all.filter((entry) => entry.status === status).length;
  const needle = filter.trim().toUpperCase();
  const visible = all
    .filter((entry) => entry.status === tab && (!needle || entry.source.includes(needle) || entry.target.includes(needle)))
    .sort((a, b) => (tab === "suggested" ? b.occurrences - a.occurrences : 0));
  const seriesName = series.data?.find((item) => item.id === seriesId)?.name ?? "";

  return (
    <main className="container wide">
      <div className="page-header">
        <h1>Glosar — {seriesName}</h1>
      </div>
      <section>
        <h2>Nova stavka</h2>
        <form
          className="glossary-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <input aria-label="Italijanski" placeholder="MICO" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} />
          <input aria-label="Srpski" placeholder="MIĆO" value={draft.target} onChange={(e) => setDraft({ ...draft, target: e.target.value })} />
          <KindSelect label="Vrsta" value={draft.kind} onChange={(kind) => setDraft({ ...draft, kind })} />
          <input aria-label="Napomena" placeholder="napomena (opciono)" value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
          <button type="submit" disabled={!draft.source.trim() || !draft.target.trim() || create.isPending}>
            Dodaj
          </button>
        </form>
        {error && <p className="error">{error.message}</p>}
      </section>
      <section>
        <h2>Predlozi iz objavljenog prevoda</h2>
        <div className="toolbar-group suggest">
          <label>
            Original{" "}
            <select aria-label="Original" value={sourceProject} onChange={(e) => setSourceProject(Number(e.target.value))}>
              <option value={0}>—</option>
              {projects.data?.map((project) => (
                <option key={project.id} value={project.id}>
                  {projectTitle(project)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Objavljeni prevod{" "}
            <select aria-label="Objavljeni prevod" value={referenceProject} onChange={(e) => setReferenceProject(Number(e.target.value))}>
              <option value={0}>—</option>
              {projects.data?.map((project) => (
                <option key={project.id} value={project.id}>
                  {projectTitle(project)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!sourceProject || !referenceProject || sourceProject === referenceProject || isActiveJob(job.data) || suggest.isPending}
            onClick={() => suggest.mutate()}
          >
            Predloži stavke
          </button>
          {job.data && <JobStatus job={job.data} />}
        </div>
        <p className="detail">Oba projekta moraju biti obrađena (pročitan tekst). Predlozi stižu u tab „Predlozi".</p>
      </section>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "approved"} onClick={() => setTab("approved")}>
          Odobreno ({count("approved")})
        </button>
        <button type="button" role="tab" aria-selected={tab === "suggested"} onClick={() => setTab("suggested")}>
          Predlozi ({count("suggested")})
        </button>
        <input className="filter" aria-label="Pretraga" placeholder="Pretraga" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      {entries.isError && <p className="error">{entries.error.message}</p>}
      {visible.length === 0 ? (
        <p className="detail">{tab === "suggested" ? "Nema predloga." : "Glosar je prazan."}</p>
      ) : (
        <table className="glossary">
          <thead>
            <tr>
              <th>Italijanski</th>
              <th>Srpski</th>
              <th>Vrsta</th>
              <th>Napomena</th>
              {tab === "suggested" && <th>Viđeno</th>}
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((entry) => (
              <GlossaryRow
                key={`${entry.id}:${entry.source}:${entry.target}:${entry.note}`}
                entry={entry}
                onChange={(changes) => update.mutate({ id: entry.id, changes })}
                onDelete={() => remove.mutate(entry.id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
