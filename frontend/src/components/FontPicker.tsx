import { ChevronDown } from "lucide-react";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { familyName, loadFont } from "../lettering/fonts";

export interface FontOption {
  value: string; // "" = podrazumevano (font serijala, automatski)
  label: string;
  key?: string; // ključ fonta za učitavanje (ugrađeni ili „user-5")
  url?: string; // fajl fonta; bez njega stavka je običnim slovima
}

const SAMPLE = "ČĆŽŠĐ Aa"; // srpska slova se odmah vide

/** Stavka za font iz spiska fontova aplikacije. */
export const fontOption = (font: { key: string; name: string; url: string }): FontOption => ({
  value: font.key,
  label: font.name,
  key: font.key,
  url: font.url,
});

/** Font za prikaz stavke: porodica iz učitanog fajla, uz rezervu ako se još učitava. */
function fontStyle(option: FontOption | undefined, loaded: Set<string>): CSSProperties {
  if (!option?.url || !option.key || !loaded.has(option.url)) return {};
  return { fontFamily: `"${familyName(option.key, option.url)}", system-ui, sans-serif` };
}

/**
 * Izbor fonta kao u programima za tekst: svaka stavka je napisana svojim fontom, uz probu srpskih slova.
 * Lista se crta preko stranice (position: fixed), pa radi i u traci alata i u panelu.
 */
export default function FontPicker({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: string;
  options: FontOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<CSSProperties>({});
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const root = useRef<HTMLDivElement>(null);
  const current = options.find((option) => option.value === value) ?? options[0];

  // fontovi se učitavaju tek kad je potrebno: izabrani odmah, ostali pri otvaranju liste
  const wanted = open ? options : current ? [current] : [];
  const wantedKey = wanted.map((option) => option.url ?? "").join("|");
  useEffect(() => {
    let alive = true;
    for (const option of wanted) {
      if (!option.url || !option.key || loaded.has(option.url)) continue;
      const url = option.url;
      loadFont(option.key, url)
        .then(() => alive && setLoaded((before) => new Set(before).add(url)))
        .catch(() => undefined);
    }
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dovoljno je kad se promeni spisak adresa
  }, [wantedKey]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  const show = () => {
    const box = root.current?.getBoundingClientRect();
    if (box) {
      const below = window.innerHeight - box.bottom;
      // u desnoj polovini ekrana lista se otvara uz desnu ivicu dugmeta, da ne izađe van prozora
      const side = box.left > window.innerWidth / 2 ? { right: Math.max(4, window.innerWidth - box.right) } : { left: Math.max(4, box.left) };
      setPlace({
        ...side,
        minWidth: Math.max(box.width, 260),
        ...(below > 260 || below > box.top ? { top: box.bottom + 2 } : { bottom: window.innerHeight - box.top + 2 }),
      });
    }
    setActive(Math.max(0, options.indexOf(current)));
    setOpen(true);
  };
  const choose = (option: FontOption) => {
    setOpen(false);
    if (option.value !== value) onChange(option.value);
  };

  return (
    <div
      className="font-picker"
      ref={root}
      onKeyDown={(event) => {
        if (!open) {
          if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            show();
          }
          return;
        }
        event.stopPropagation(); // strelice i Esc ne idu editoru dok je lista otvorena
        if (event.key === "Escape") setOpen(false);
        if (event.key === "ArrowDown") setActive((index) => Math.min(options.length - 1, index + 1));
        if (event.key === "ArrowUp") setActive((index) => Math.max(0, index - 1));
        if (event.key === "Enter") choose(options[active]);
        if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) event.preventDefault();
      }}
    >
      <button
        type="button"
        className="font-picker-button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          if (open) setOpen(false);
          else show();
        }}
      >
        <span style={fontStyle(current, loaded)}>{current?.label ?? "—"}</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <ul className="font-picker-list" role="listbox" aria-label={ariaLabel} style={place} onClick={(event) => event.stopPropagation()}>
          {options.map((option, index) => (
            <li
              key={option.value || "podrazumevano"}
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "active" : ""}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option)}
            >
              <span className="font-picker-name" style={fontStyle(option, loaded)}>
                {option.label}
              </span>
              {option.url && (
                <span className="font-picker-sample" style={fontStyle(option, loaded)}>
                  {SAMPLE}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
