import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getHealth, runLlm } from "../api";
import JobQueue from "../components/JobQueue";

function StatusRow({ label, ok, detail }: { label: string; ok?: boolean; detail?: string }) {
  const state = ok === undefined ? "pending" : ok ? "ok" : "error";
  return (
    <li className={`status status-${state}`} data-testid={`status-${label}`}>
      <span className="dot" aria-hidden="true" />
      <strong>{label}</strong>
      {detail && <span className="detail">{detail}</span>}
    </li>
  );
}

export default function StatusPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 5000 });
  const llm = useMutation({ mutationFn: runLlm });
  const [prompt, setPrompt] = useState("Prevedi na srpski, samo prevod: Non abbiamo tempo adesso.");
  const h = health.data;
  const llama = h?.llama_server;

  const workerDetail =
    h &&
    (h.worker.last_seen
      ? `poslednji signal ${new Date(h.worker.last_seen).toLocaleTimeString("sr-Latn")}`
      : "nema signala");

  return (
    <main className="container">

      <section>
        <h2>Status sistema</h2>
        <ul className="statuses">
          <StatusRow
            label="API"
            ok={health.isPending ? undefined : !health.isError}
            detail={health.error?.message}
          />
          <StatusRow label="Baza" ok={h?.database.ok} detail={h?.database.error} />
          <StatusRow label="Worker" ok={h?.worker.ok} detail={workerDetail} />
          <StatusRow
            label={llama?.server === "ollama" ? "Ollama" : "llama-server"}
            ok={llama?.ok}
            detail={llama && (llama.ok ? `${llama.version} · ${llama.url}` : llama.error)}
          />
        </ul>
        {llama?.models && llama.models.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>OCR model</th>
                <th>Fajl</th>
                <th>Mogućnosti</th>
              </tr>
            </thead>
            <tbody>
              {llama.models.map((model) => (
                <tr key={model.name}>
                  <td>{model.name}</td>
                  <td>{model.file ?? "—"}</td>
                  <td>{model.capabilities.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>Poslovi</h2>
        <JobQueue />
      </section>

      <section>
        <h2>Test LLM-a</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            llm.mutate(prompt);
          }}
        >
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} />
          <button type="submit" disabled={llm.isPending || !prompt.trim()}>
            {llm.isPending ? "Radi…" : "Pokreni"}
          </button>
        </form>
        {llm.isError && <p className="error">{llm.error.message}</p>}
        {llm.data && (
          <div className="result">
            <p>{llm.data.response}</p>
            <p className="detail">
              {llm.data.model} · prompt{" "}
              {llm.data.prompt_tokens_per_second} tok/s · generisanje{" "}
              {llm.data.eval_tokens_per_second} tok/s
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
