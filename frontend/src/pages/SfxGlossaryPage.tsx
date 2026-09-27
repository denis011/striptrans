import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type SfxChanges, type SfxEntry, type SfxMissing, createSfx, deleteSfx, listMissingSfx, listSfx, updateSfx } from "../api";

function SfxRow({ entry, onChange, onDelete }: { entry: SfxEntry; onChange: (changes: SfxChanges) => void; onDelete: () => void }) {
  const [source, setSource] = useState(entry.source);
  const [target, setTarget] = useState(entry.target);
  const [note, setNote] = useState(entry.note ?? "");
  const saveText = (field: "source" | "target", value: string, original: string) => {
    if (value.trim() && value !== original) onChange({ [field]: value });
  };

  return (
    <tr>
      <td>
        <input aria-label={`Original: ${entry.source}`} value={source} onChange={(e) => setSource(e.target.value)} onBlur={() => saveText("source", source, entry.source)} />
      </td>
      <td>
        <input aria-label={`Srpski: ${entry.source}`} value={target} onChange={(e) => setTarget(e.target.value)} onBlur={() => saveText("target", target, entry.target)} />
      </td>
      <td>
        <input aria-label={`Napomena: ${entry.source}`} value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => note !== (entry.note ?? "") && onChange({ note })} />
      </td>
      <td className="row-actions">
        <button type="button" className="icon" aria-label={`Obriši ${entry.source}`} onClick={() => window.confirm(`Obrisati „${entry.source}“?`) && onDelete()}>
          ✕
        </button>
      </td>
    </tr>
  );
}

/** Reč koje nema u glosaru: predlog po pravilu se ispravi i doda jednim klikom. */
function MissingRow({ item, onAdd }: { item: SfxMissing; onAdd: (target: string) => void }) {
  const [target, setTarget] = useState(item.suggestion);
  return (
    <tr>
      <td>{item.source}</td>
      <td>
        <input aria-label={`Prevod: ${item.source}`} value={target} onChange={(e) => setTarget(e.target.value)} />
      </td>
      <td className="detail">{item.count}×</td>
      <td className="row-actions">
        <button type="button" aria-label={`Dodaj ${item.source}`} disabled={!target.trim()} onClick={() => onAdd(target)}>
          Dodaj
        </button>
      </td>
    </tr>
  );
}

export default function SfxGlossaryPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"glossary" | "missing">("glossary");
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState({ source: "", target: "", note: "" });
  const entries = useQuery({ queryKey: ["sfx-glossary"], queryFn: listSfx });
  const missing = useQuery({ queryKey: ["sfx-glossary", "missing"], queryFn: listMissingSfx });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["sfx-glossary"] });
  const create = useMutation({
    mutationFn: (entry: { source: string; target: string; note?: string }) => createSfx(entry),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: SfxChanges }) => updateSfx(id, changes),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: deleteSfx, onSuccess: refresh });
  const error = [create, update, remove].find((mutation) => mutation.error)?.error;

  const needle = filter.trim().toUpperCase();
  const matches = (...texts: string[]) => !needle || texts.some((text) => text.includes(needle));
  const visible = (entries.data ?? []).filter((entry) => matches(entry.source, entry.target));
  const unknown = (missing.data ?? []).filter((item) => matches(item.source));

  return (
    <main className="container wide">
      <div className="page-header">
        <h1>Glosar onomatopeja</h1>
      </div>
      <p className="detail">
        Zajednički za sve serijale. Onomatopeje se ne šalju modelu na prevod: prvo se traži glosar, a reč koje nema u glosaru
        ostaje ista, osim ako ima SH ili W (CRASH → KRAŠ, SWISH → SVIŠ). Na projektu dugme „Onomatopeje po glosaru“ primenjuje
        izmene na već prevedene stranice.
      </p>
      <section>
        <h2>Nova stavka</h2>
        <form
          className="glossary-form sfx-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(
              { source: draft.source, target: draft.target, note: draft.note || undefined },
              { onSuccess: () => setDraft({ source: "", target: "", note: "" }) },
            );
          }}
        >
          <input aria-label="Original" placeholder="SWISH" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} />
          <input aria-label="Srpski" placeholder="SVIŠ" value={draft.target} onChange={(e) => setDraft({ ...draft, target: e.target.value })} />
          <input aria-label="Napomena" placeholder="napomena (opciono)" value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
          <button type="submit" disabled={!draft.source.trim() || !draft.target.trim() || create.isPending}>
            Dodaj
          </button>
        </form>
        {error && <p className="error">{error.message}</p>}
      </section>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "glossary"} onClick={() => setTab("glossary")}>
          U glosaru ({entries.data?.length ?? 0})
        </button>
        <button type="button" role="tab" aria-selected={tab === "missing"} onClick={() => setTab("missing")}>
          Nisu u glosaru ({missing.data?.length ?? 0})
        </button>
        <input className="filter" aria-label="Pretraga" placeholder="Pretraga" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      {tab === "glossary" &&
        (visible.length === 0 ? (
          <p className="detail">Glosar je prazan.</p>
        ) : (
          <table className="glossary">
            <thead>
              <tr>
                <th>Original</th>
                <th>Srpski</th>
                <th>Napomena</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((entry) => (
                <SfxRow
                  key={`${entry.id}:${entry.source}:${entry.target}:${entry.note}`}
                  entry={entry}
                  onChange={(changes) => update.mutate({ id: entry.id, changes })}
                  onDelete={() => remove.mutate(entry.id)}
                />
              ))}
            </tbody>
          </table>
        ))}
      {tab === "missing" &&
        (unknown.length === 0 ? (
          <p className="detail">Sve reči onomatopeja iz projekata su u glosaru.</p>
        ) : (
          <>
            <p className="detail">Reči onomatopeja iz svih projekata kojih nema u glosaru; predlog je po pravilu (SH i W).</p>
            <table className="glossary missing">
              <thead>
                <tr>
                  <th>Original</th>
                  <th>Srpski</th>
                  <th>Viđeno</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {unknown.map((item) => (
                  <MissingRow key={item.source} item={item} onAdd={(target) => create.mutate({ source: item.source, target })} />
                ))}
              </tbody>
            </table>
          </>
        ))}
    </main>
  );
}
