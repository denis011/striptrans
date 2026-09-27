import { NavLink, Route, Routes, useMatch } from "react-router";
import ThemeToggle from "./components/ThemeToggle";
import ExportPage from "./pages/ExportPage";
import GlossaryPage from "./pages/GlossaryPage";
import ProjectPage from "./pages/ProjectPage";
import ProjectsPage from "./pages/ProjectsPage";
import RatingsPage from "./pages/RatingsPage";
import StatusPage from "./pages/StatusPage";
import ViewerPage from "./pages/ViewerPage";

// razvojno okruženje (docker-compose.dev.yml): crveni okvir i natpis na svakoj strani, da se u kopiji
// podataka ne radi posao koji treba da ostane (lektura u DEV-u se gubi pri osvežavanju kopije)
const DEV = import.meta.env.VITE_APP_ENV === "DEV";
if (DEV && typeof document !== "undefined") document.title = `DEV — ${document.title}`;

export function DevBanner() {
  return (
    <div className="dev-frame" role="note" aria-label="Razvojno okruženje">
      <span>DEV — razvojna kopija, izmene se ne čuvaju · pravi rad na localhost:5173</span>
    </div>
  );
}

export default function App() {
  // editor ima svoje zaglavlje (Faza 7a), da stranici ostane što više mesta
  const editor = useMatch("/projects/:projectId/pages/:position");
  return (
    <>
      {DEV && <DevBanner />}
      {!editor && (
      <header className="topbar">
        <NavLink to="/" className="brand">
          StripTrans
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Projekti
          </NavLink>
          <NavLink to="/status">Status</NavLink>
        </nav>
        <ThemeToggle />
      </header>
      )}
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="/projects/:projectId/export" element={<ExportPage />} />
        <Route path="/series/:seriesId/glossary" element={<GlossaryPage />} />
        <Route path="/ratings/:study" element={<RatingsPage />} />
        <Route path="/projects/:projectId/pages/:position" element={<ViewerPage />} />
        <Route
          path="*"
          element={
            <main className="container">
              <p>Stranica ne postoji.</p>
            </main>
          }
        />
      </Routes>
    </>
  );
}
