// Ctrl+B i dugme B u poljima za tekst: naglasak oko izbora ili reči pod kursorom (vidi toggleEmphasis).

import type { KeyboardEvent } from "react";
import { toggleEmphasis } from "./emphasis";

/** Naglasi izbor u polju i vrati kursor/izbor na naglašen deo; vraća novi tekst. */
export function emphasizeSelection(field: HTMLTextAreaElement, setValue: (text: string) => void): string {
  const edit = toggleEmphasis(field.value, field.selectionStart, field.selectionEnd);
  setValue(edit.text);
  // izbor se postavlja kad React upiše novu vrednost u polje
  requestAnimationFrame(() => field.setSelectionRange(edit.start, edit.end));
  return edit.text;
}

export function isEmphasisKey(event: KeyboardEvent): boolean {
  return (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "b";
}
