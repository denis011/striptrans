// Svetla i tamna tema (Faza 7b): atribut data-theme na <html>; „kao sistem" ga uklanja, pa važi
// prefers-color-scheme. Isti ključ čita i skripta u index.html, da ekran ne trepne pri učitavanju.

import { loadSetting, saveSetting } from "./storage";

export type Theme = "system" | "light" | "dark";

export const THEME_KEY = "striptrans.theme";
export const THEMES: Theme[] = ["system", "light", "dark"];

export function loadTheme(): Theme {
  const theme = loadSetting<Theme>(THEME_KEY, "system");
  return THEMES.includes(theme) ? theme : "system";
}

export function applyTheme(theme: Theme): void {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
}

export function saveTheme(theme: Theme): void {
  saveSetting(THEME_KEY, theme);
  applyTheme(theme);
}
