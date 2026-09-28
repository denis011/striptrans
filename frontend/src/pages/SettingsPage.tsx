import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type TranslationStyle, activateStyle, createStyle, deleteStyle, listStyles, resetStyle, updateStyle } from "../api";

/** Uređivanje jednog stila: ime i tekst se čuvaju dugmetom, da se ne šalje svako slovo. */
function StyleEditor({ style, onSaved }: { style: TranslationStyle; onSaved: () => void }) {
  const [name, setName] = useState(style.name);
  const [text, setText] = useState(style.text);
  const save = useMutation({ mutationFn: () => updateStyle(style.id, { name, text }), onSuccess: onSaved });
  const reset = useMutation({ mutationFn: () => resetStyle(style.id), onSuccess: onSaved });
  const activate = useMutation({ mutationFn: () => activateStyle(style.id), onSuccess: onSaved });
  const remove = useMutation({ mutationFn: () => deleteStyle(style.id), onSuccess: onSaved });
  const error = [save, reset, activate, remove].find((mutation) => mutation.error)?.error;
  const dirty = name !== style.name || text !== style.text;

  return (
    <div className="style-editor">
      <label>
        Ime stila
        <input aria-label="Ime stila" value={name} disabled={style.builtin} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Uputstvo za stil prevoda
        <textarea aria-label="Uputstvo za stil prevoda" rows={16} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="toolbar-group">
        <button type="button" disabled={!dirty || !name.trim() || save.isPending} onClick={() => save.mutate()}>
          Sačuvaj
        </button>
        {!style.active && (
          <button type="button" onClick={() => activate.mutate()}>
            Koristi ovaj stil
          </button>
        )}
        {style.builtin ? (
          <button type="button" disabled={!style.changed || reset.isPending} onClick={() => reset.mutate()}>
            Vrati podrazumevano
          </button>
        ) : (
          <button type="button" onClick={() => window.confirm(`Obrisati stil „${style.name}“?`) && remove.mutate()}>
            Obriši stil
          </button>
        )}
        {style.active && <span className="badge">aktivan</span>}
      </div>
      {error && <p className="error">{error.message}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const styles = useQuery({ queryKey: ["translation-styles"], queryFn: listStyles });
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["translation-styles"] });
  const all = styles.data ?? [];
  const chosen = all.find((style) => style.id === chosenId) ?? all.find((style) => style.active) ?? all[0];
  const create = useMutation({
    // nov stil počinje od izabranog, pa se menja samo ono što treba
    mutationFn: () => createStyle({ name: newName.trim(), text: chosen?.text ?? "" }),
    onSuccess: (style) => {
      setNewName("");
      setChosenId(style.id);
      refresh();
    },
  });

  return (
    <main className="container wide">
      <div className="page-header">
        <h1>Podešavanja</h1>
      </div>
      <section>
        <h2>Stil prevoda</h2>
        <p className="detail">
          Stil opisuje kako prevod treba da zvuči: ton naracije, govor likova, kletve i uzvici, koliko skraćivati. Aktivni stil koristi svaki
          sledeći prevod. Pravila od kojih zavisi rad aplikacije (numeracija, kolone, naglasak, latinica, srpski ekavski) su fiksna i nisu ovde.
          Likovi i uzrečice jednog serijala idu u „Uputstvo za prevod serijala“ na strani Glosar. U panelu bloka „Probni prevod“ prevodi blok
          izabranim stilom bez upisa.
        </p>
        {styles.isError && <p className="error">{styles.error.message}</p>}
        <div className="styles-layout">
          <ul className="style-list">
            {all.map((style) => (
              <li key={style.id}>
                <button type="button" aria-pressed={style.id === chosen?.id} onClick={() => setChosenId(style.id)}>
                  {style.name}
                  {style.active && " ✓"}
                </button>
              </li>
            ))}
            <li>
              <form
                className="new-style"
                onSubmit={(event) => {
                  event.preventDefault();
                  create.mutate();
                }}
              >
                <input aria-label="Ime novog stila" placeholder="nov stil (kopija izabranog)" value={newName} onChange={(event) => setNewName(event.target.value)} />
                <button type="submit" disabled={!newName.trim() || create.isPending}>
                  Dodaj
                </button>
              </form>
              {create.isError && <p className="error">{create.error.message}</p>}
            </li>
          </ul>
          {chosen && <StyleEditor key={`${chosen.id}:${chosen.name}:${chosen.text}`} style={chosen} onSaved={refresh} />}
        </div>
      </section>
    </main>
  );
}
