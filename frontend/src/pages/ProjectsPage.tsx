import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  createProject,
  importPages,
  listProjects,
  listSeries,
  pageThumbnailUrl,
  projectTitle,
} from "../api";
import FileDrop from "../components/FileDrop";

function fileLabel(files: File[], empty: string): string {
  return files.length > 0 ? files.map((file) => file.name).join(", ") : empty;
}

function NewProjectForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const series = useQuery({ queryKey: ["series"], queryFn: listSeries });
  const [form, setForm] = useState({ seriesId: "", issue: "", originalTitle: "", translatedTitle: "" });
  const [original, setOriginal] = useState<File[]>([]);
  const [reference, setReference] = useState<File[]>([]);
  const seriesId = form.seriesId || String(series.data?.[0]?.id ?? "");

  const create = useMutation({
    mutationFn: async () => {
      const project = await createProject({
        series_id: Number(seriesId),
        issue_number: form.issue || undefined,
        original_title: form.originalTitle || undefined,
        translated_title: form.translatedTitle || undefined,
      });
      if (original.length > 0) await importPages(project.id, "original", original);
      if (reference.length > 0) await importPages(project.id, "reference", reference);
      return project;
    },
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${project.id}`);
    },
  });

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: event.target.value }),
  });

  return (
    <section>
      <h2>Novi projekat</h2>
      <form
        className="grid-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <label>
          Serijal
          <select {...field("seriesId")} value={seriesId}>
            {series.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Broj
          <input {...field("issue")} placeholder="12" />
        </label>
        <label>
          Originalni naslov
          <input {...field("originalTitle")} placeholder="La valle del silenzio" />
        </label>
        <label>
          Srpski naslov
          <input {...field("translatedTitle")} placeholder="Dolina tišine" />
        </label>
        <div className="full">
          <span>Original (italijansko izdanje)</span>
          <FileDrop onFiles={setOriginal} label={fileLabel(original, "Prevuci fajlove originala")} />
        </div>
        <div className="full">
          <span>Referentno izdanje (opciono)</span>
          <FileDrop
            onFiles={setReference}
            label={fileLabel(reference, "Prevuci fajlove referentnog izdanja")}
          />
        </div>
        <div className="full">
          <button type="submit" disabled={!seriesId || create.isPending}>
            {create.isPending ? "Šaljem…" : "Napravi projekat"}
          </button>
          {create.isError && <span className="error">{create.error.message}</span>}
        </div>
      </form>
    </section>
  );
}

export default function ProjectsPage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  return (
    <main className="container">
      <NewProjectForm />
      <section>
        <h2>Projekti</h2>
        {projects.isPending && <p>Učitavanje…</p>}
        {projects.isError && <p className="error">{projects.error.message}</p>}
        {projects.data?.length === 0 && <p className="detail">Još nema projekata.</p>}
        <ul className="project-list">
          {projects.data?.map((project) => (
            <li key={project.id}>
              <Link to={`/projects/${project.id}`} className="project-card">
                {project.cover_page_id ? (
                  <img src={pageThumbnailUrl(project.cover_page_id)} alt="" />
                ) : (
                  <div className="no-cover" />
                )}
                <div>
                  <strong>{projectTitle(project)}</strong>
                  <span className="detail">
                    {project.page_count} stranica
                    {project.reference_page_count > 0 &&
                      ` · referenca ${project.reference_page_count}`}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
