import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { THEMES, type Theme, loadTheme, saveTheme } from "../theme";

const LABELS: Record<Theme, string> = { system: "kao sistem", light: "svetla", dark: "tamna" };
const ICONS = { system: Monitor, light: Sun, dark: Moon };

/** Prekidač teme: kao sistem → svetla → tamna. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const Icon = ICONS[theme];
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  return (
    <button
      type="button"
      className="icon-button"
      aria-label={`Tema: ${LABELS[theme]}`}
      title={`Tema: ${LABELS[theme]} (klik: ${LABELS[next]})`}
      onClick={() => {
        saveTheme(next);
        setTheme(next);
      }}
    >
      <Icon size={18} aria-hidden />
    </button>
  );
}
