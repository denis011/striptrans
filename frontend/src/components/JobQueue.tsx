import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { cancelJob, listActiveJobs, type ActiveJob } from "../api";
import JobStatus from "./JobStatus";

// dugi poslovi: samo za njih ima smisla procena vremena
const LONG_JOBS = new Set(["process_project", "translate_project", "clean_project", "prepare_project", "export_draw"]);
const MIN_SAMPLE_MS = 60_000; // tempo se meri tek posle minut rada

export interface Sample {
  at: number;
  progress: number;
}

/** Trajanje celog posla (ms) iz tempa od prvog viđenja; null dok nema dovoljno podataka. */
export function jobDuration(first: Sample, now: Sample, total: number): number | null {
  const elapsed = now.at - first.at;
  const done = now.progress - first.progress;
  if (elapsed < MIN_SAMPLE_MS || done <= 0 || total <= 0) return null;
  return (total * elapsed) / done;
}

export function formatDuration(ms: number): string {
  const minutes = Math.max(1, Math.round(ms / 60_000));
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}

/** Red poslova: posao koji radi, sa procenom, i poslovi koji čekaju, redom kojim će doći na red. */
export default function JobQueue() {
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs", "active"], queryFn: listActiveJobs, refetchInterval: 3000 });
  const cancel = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs", "active"] }),
  });
  const firstSeen = useRef(new Map<number, Sample>());
  const list: ActiveJob[] = Array.isArray(jobs.data) ? jobs.data : [];
  const running = list.find((job) => job.status === "running");
  const queued = list.filter((job) => job.status === "queued");

  let remaining: number | null = null;
  let rest: number | null = null;
  if (running && LONG_JOBS.has(running.type)) {
    const now = { at: Date.now(), progress: running.progress };
    if (!firstSeen.current.has(running.id)) firstSeen.current.set(running.id, now);
    const duration = jobDuration(firstSeen.current.get(running.id)!, now, running.total);
    if (duration !== null) {
      remaining = (duration * (running.total - running.progress)) / running.total;
      // poslovi iste vrste koji čekaju traju otprilike isto kao ovaj
      rest = remaining + duration * queued.filter((job) => job.type === running.type).length;
    }
  }

  if (jobs.isPending) return <p className="detail">Učitavam red poslova…</p>;
  if (!list.length) return <p className="detail">Nema poslova u redu.</p>;
  return (
    <div className="job-queue">
      <p>
        Radi: {running ? 1 : 0} · čeka: {queued.length}
        {rest !== null && ` · procena do kraja reda: ~${formatDuration(rest)}`}
      </p>
      {running && (
        <div className="job-row">
          <strong>{running.project_title ?? "bez projekta"}</strong>
          <JobStatus job={running} onCancel={(id) => cancel.mutate(id)} />
          {remaining !== null && <span className="detail">još ~{formatDuration(remaining)}</span>}
        </div>
      )}
      {queued.length > 0 && (
        <ol className="queued">
          {queued.map((job) => (
            <li key={job.id}>
              {job.project_title ?? "bez projekta"} — <JobStatus job={job} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
