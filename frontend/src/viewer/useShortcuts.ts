import { useEffect, useEffectEvent } from "react";
import { nudgeForKey } from "./navigation";

export type ShortcutMode = "select" | "draw" | "brush" | "text" | "patch";

/** Radnje editora koje pokreću prečice; raspored tastera je ovde, na jednom mestu. */
export interface ShortcutActions {
  approve: (wholePage: boolean) => void; // Ctrl+Enter, uz Shift cela stranica
  escape: () => void;
  remove: () => boolean; // Delete: true ako je nešto obrisano
  history: (kind: "undo" | "redo") => void;
  toggleMode: (mode: ShortcutMode) => void;
  pending: () => void; // U: sledeći neodobren blok
  read: () => void; // R: OCR izabranih blokova
  nextForAi: () => void; // G: sledeći naslov, natpis ili zvuk bez zakrpe, isečak u clipboard
  nudge: (dx: number, dy: number) => boolean; // strelice: true ako je nešto pomereno
  turnPage: (key: string) => boolean; // strelice, Home, End… bez izbora: druga stranica
}

const MODE_KEYS: Record<string, ShortcutMode> = { n: "draw", b: "brush", t: "text", p: "patch" };

export function isTyping(target: EventTarget | null): target is HTMLElement {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}

/** Prečice sa tastature za ceo prozor; dok se kuca u polje, važi samo Esc (napušta polje). */
export function useShortcuts(actions: ShortcutActions) {
  const onKey = useEffectEvent((event: KeyboardEvent) => {
    if (isTyping(event.target)) {
      if (event.key === "Escape") event.target.blur();
      return;
    }
    const command = event.ctrlKey || event.metaKey;
    const plain = !command && !event.altKey;
    const key = event.key.toLowerCase();
    if (event.key === "Enter" && command) {
      event.preventDefault();
      actions.approve(event.shiftKey);
    } else if (event.key === "Escape") {
      actions.escape();
    } else if ((event.key === "Delete" || event.key === "Backspace") && actions.remove()) {
      event.preventDefault();
    } else if (command && (key === "z" || key === "y")) {
      event.preventDefault();
      actions.history(key === "y" || event.shiftKey ? "redo" : "undo");
    } else if (plain && key in MODE_KEYS) {
      actions.toggleMode(MODE_KEYS[key]);
    } else if (plain && key === "u") {
      actions.pending();
    } else if (plain && key === "r") {
      actions.read();
    } else if (plain && key === "g") {
      actions.nextForAi();
    } else {
      const delta = command || event.altKey ? null : nudgeForKey(event.key, event.shiftKey);
      if ((delta && actions.nudge(delta[0], delta[1])) || actions.turnPage(event.key)) event.preventDefault();
    }
  });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => onKey(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
}
