import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { type RatingStudy, getRatingStudy, getRatingSummary, rateTranslation } from "../api";

const LABELS = "ABCDEFGH";
const SCALE: [number, string][] = [
  [5, "odlično, bez izmena"],
  [4, "sitne izmene"],
  [3, "potrebne izmene"],
  [2, "loše"],
  [1, "neupotrebljivo"],
];

function Summary({ study }: { study: string }) {
  const summary = useQuery({ queryKey: ["rating-summary", study], queryFn: () => getRatingSummary(study) });
  if (!summary.data) return null;
  return (
    <section>
      <h2>Rezultat</h2>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Prosečna ocena</th>
            <th>Ocena 4–5</th>
            <th>Prevoda</th>
          </tr>
        </thead>
        <tbody>
          {summary.data.candidates.map((row) => (
            <tr key={row.candidate}>
              <td>{row.candidate}</td>
              <td>{row.average.toFixed(2)}</td>
              <td>{Math.round(row.good_share * 100)} %</td>
              <td>{row.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function RatingsPage() {
  const study = useParams().study ?? "";
  const queryClient = useQueryClient();
  const data = useQuery({ queryKey: ["ratings", study], queryFn: () => getRatingStudy(study) });
  const [chosen, setChosen] = useState<number | null>(null);
  const rate = useMutation({
    mutationFn: ({ id, score }: { id: number; score: number }) => rateTranslation(study, id, score),
    onSuccess: (candidate) =>
      queryClient.setQueryData<RatingStudy>(["ratings", study], (old) => {
        if (!old) return old;
        const items = old.items.map((item) => ({
          ...item,
          candidates: item.candidates.map((c) => (c.id === candidate.id ? { ...c, score: candidate.score } : c)),
        }));
        const rated = items.filter((item) => item.candidates.every((c) => c.score !== null)).length;
        return { ...old, items, rated_items: rated };
      }),
  });

  if (data.isPending) return <main className="container">Učitavanje…</main>;
  if (data.isError) {
    return (
      <main className="container">
        <p className="error">{data.error.message}</p>
      </main>
    );
  }

  const { items, total_items: total, rated_items: rated } = data.data;
  const firstOpen = items.findIndex((item) => item.candidates.some((c) => c.score === null));
  const index = chosen ?? (firstOpen === -1 ? items.length - 1 : firstOpen);
  const item = items[index];
  const candidates = [...item.candidates].sort((a, b) => a.order - b.order);

  return (
    <main className="container">
      <div className="page-header">
        <div>
          <h1>Slepa ocena prevoda</h1>
          <span className="detail" data-testid="rating-progress">
            Ocenjeno {rated} / {total} blokova
          </span>
        </div>
        <div className="actions">
          <button type="button" disabled={index === 0} onClick={() => setChosen(index - 1)}>
            ‹ Prethodni
          </button>
          <span>
            {index + 1} / {total}
          </span>
          <button type="button" disabled={index === items.length - 1} onClick={() => setChosen(index + 1)}>
            Sledeći ›
          </button>
        </div>
      </div>
      <section>
        <p className="detail">
          Str. {item.page_position}, blok {item.block_position}
        </p>
        <p className="rating-source">{item.source}</p>
        {candidates.map((candidate, position) => (
          <div key={candidate.id} className="rating-candidate">
            <strong>{LABELS[position]}</strong>
            <span className="rating-translation">{candidate.translation}</span>
            <span className="rating-scores">
              {[1, 2, 3, 4, 5].map((score) => (
                <button
                  key={score}
                  type="button"
                  className={candidate.score === score ? "active" : ""}
                  aria-label={`Prevod ${LABELS[position]}: ocena ${score}`}
                  onClick={() => rate.mutate({ id: candidate.id, score })}
                >
                  {score}
                </button>
              ))}
            </span>
          </div>
        ))}
        {rate.isError && <p className="error">{rate.error.message}</p>}
        <p className="detail">{SCALE.map(([score, label]) => `${score} = ${label}`).join(" · ")}</p>
      </section>
      {rated === total && <Summary study={study} />}
    </main>
  );
}
