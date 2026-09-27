import type { Job } from "../api";

const LABELS: Record<string, string> = {
  import: "Uvoz",
  process_page: "Obrada stranice",
  process_project: "Obrada",
  glossary_suggest: "Predlozi za glosar",
  translate_page: "Prevod stranice",
  translate_project: "Prevod",
  clean_page: "Čišćenje stranice",
  clean_project: "Čišćenje",
  prepare_project: "Priprema albuma",
  export: "Pakovanje albuma",
  export_draw: "Crtanje albuma", // crta browser (tab „Izvoz albuma"); nije posao workera
};

export function isActiveJob(job?: Job | null): boolean {
  return job?.status === "queued" || job?.status === "running";
}

export default function JobStatus({ job, onCancel }: { job: Job; onCancel?: (id: number) => void }) {
  const stage = job.status === "running" && typeof job.result?.stage === "string" ? ` (${job.result.stage})` : "";
  const label = (LABELS[job.type] ?? job.type) + stage;
  if (job.status === "failed") return <span className="error">{label}: greška — {job.error}</span>;
  if (job.status === "cancelled") return <span className="detail">{label}: prekinuto</span>;
  if (job.status === "done") return <span className="detail">{label}: završeno</span>;
  return (
    <span className="job" data-testid="job-progress">
      <span>{job.status === "queued" ? `${label} čeka na red…` : `${label}: ${job.progress} / ${job.total}`}</span>
      <progress max={job.total || 1} value={job.progress} />
      {onCancel && job.type !== "import" && job.id > 0 && (
        <button type="button" disabled={job.cancel_requested} onClick={() => onCancel(job.id)}>
          {job.cancel_requested ? "Prekidam…" : "Prekini"}
        </button>
      )}
    </span>
  );
}
