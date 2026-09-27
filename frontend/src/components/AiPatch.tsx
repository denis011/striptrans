import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { type TextBlock, acceptAiPatch, aiImageUrl, getJob, listAiProposals, pageCropUrl, requestAiPatch } from "../api";
import { isActiveJob } from "./JobStatus";

export const AI_KINDS = new Set(["title", "other", "sfx"]); // naslovi, natpisi i onomatopeje

const QUALITIES = {
  quality: "kvalitetno (~0,07 $)",
  cheap: "jeftino (~0,03 $)",
} as const;
type Quality = keyof typeof QUALITIES;
const MARGIN = 0.12; // isti isečak kao na serveru: blok + 12 % sa svake strane

/**
 * AI prepravka natpisa: model za slike crta prevod istim slovima na isečku originala. Svaki predlog se
 * plaća, pa se čuva: bira se među ranijim predlozima i prihvata (bez novog poziva), a prihvaćen postaje
 * zakrpa preko natpisa (Ctrl+Z je vraća).
 */
export default function AiPatch({ block }: { block: TextBlock }) {
  const queryClient = useQueryClient();
  const [quality, setQuality] = useState<Quality>(block.kind === "sfx" ? "cheap" : "quality");
  const [pending, setPending] = useState<number | null>(null); // predlog koji model upravo crta
  const [chosen, setChosen] = useState<number | null>(null);
  const [hidden, setHidden] = useState(false);
  const proposals = useQuery({ queryKey: ["ai-proposals", block.id], queryFn: () => listAiProposals(block.id) });
  const job = useQuery({
    queryKey: ["job", pending],
    queryFn: () => getJob(pending!),
    enabled: pending !== null,
    refetchInterval: (query) => (isActiveJob(query.state.data) ? 1500 : false),
  });
  const running = pending !== null && isActiveJob(job.data);
  const finished = pending !== null && job.data && !isActiveJob(job.data) ? job.data : null;
  useEffect(() => {
    // gotov predlog ulazi u spisak plaćenih i odmah je izabran
    if (!finished) return;
    if (finished.status === "done") setChosen(finished.id);
    queryClient.invalidateQueries({ queryKey: ["ai-proposals", block.id] });
    queryClient.invalidateQueries({ queryKey: ["project"] });
    setPending(null);
    setHidden(false);
  }, [finished, queryClient, block.id]);
  const request = useMutation({
    mutationFn: () => requestAiPatch(block.id, quality),
    onSuccess: (created) => setPending(created.id),
  });
  const accept = useMutation({
    mutationFn: (id: number) => acceptAiPatch(id),
    onSuccess: () => {
      for (const key of [["patches", block.page_id], ["history", block.page_id]]) queryClient.invalidateQueries({ queryKey: key });
      setHidden(true);
    },
  });
  const list = proposals.data ?? [];
  const selected = list.find((item) => item.job_id === chosen) ?? list[0];
  const label = `blok ${block.position}`;
  const mx = block.width * MARGIN;
  const my = block.height * MARGIN;
  const crop = { x: Math.max(0, block.x - mx), y: Math.max(0, block.y - my), width: block.width + 2 * mx, height: block.height + 2 * my };

  return (
    <div className="ai-patch" onClick={(event) => event.stopPropagation()}>
      <div className="ai-patch-head">
        <button type="button" className="small" disabled={running || request.isPending} aria-label={`Prepravi AI-jem (${label})`} onClick={() => request.mutate()}
          title="Nov predlog: model za slike crta prevod istim slovima na isečku originala (plaća se; slika ide na OpenRouter)">
          {running || request.isPending ? "AI crta…" : list.length ? "Nov predlog" : "Prepravi AI-jem"}
        </button>
        <select aria-label={`Kvalitet AI prepravke (${label})`} value={quality} disabled={running} onChange={(event) => setQuality(event.target.value as Quality)}>
          {Object.entries(QUALITIES).map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </div>
      {request.isError && <p className="error">{request.error.message}</p>}
      {job.data?.status === "failed" && <p className="error">AI prepravka nije uspela: {job.data.error}</p>}
      {selected && !hidden && (
        <div className="ai-patch-result">
          <img alt="Original" src={pageCropUrl(block.page_id, crop, false)} />
          <img alt="Predlog AI prepravke" src={aiImageUrl(selected.job_id)} />
          <span className="detail">proveri slova pre prihvatanja · već plaćeno, prihvatanje je besplatno</span>
          <div className="ai-patch-actions">
            <button type="button" className="small" aria-label={`Prihvati AI prepravku (${label})`} disabled={accept.isPending} onClick={() => accept.mutate(selected.job_id)}>
              Prihvati
            </button>
            <button type="button" className="small" aria-label={`Sakrij AI prepravku (${label})`} onClick={() => setHidden(true)}>
              Sakrij
            </button>
          </div>
        </div>
      )}
      {list.length > 1 && (
        <div className="ai-patch-list" aria-label={`Plaćeni predlozi (${label})`}>
          {list.map((item) => (
            <button key={item.job_id} type="button" className={`ai-thumb${item.job_id === selected?.job_id ? " active" : ""}`}
              aria-label={`Predlog ${item.job_id} (${label})`} title={`${item.model.replace("or:google/", "")} · ${item.cost?.toFixed(3) ?? "?"} $`}
              onClick={() => { setChosen(item.job_id); setHidden(false); }}>
              <img alt="" src={aiImageUrl(item.job_id)} />
            </button>
          ))}
        </div>
      )}
      {hidden && list.length > 0 && (
        <button type="button" className="small" onClick={() => setHidden(false)}>
          Plaćeni predlozi ({list.length})
        </button>
      )}
    </div>
  );
}
