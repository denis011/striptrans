import { ChevronDown } from "lucide-react";
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";

interface Props {
  label: string; // naziv dugmeta i grupe (za čitače ekrana i testove)
  icon?: ReactNode;
  text?: string; // vidljiv tekst dugmeta (podrazumevano label)
  title?: string;
  align?: "left" | "right";
  children: ReactNode;
}

/**
 * Padajući meni trake alata. Klik na dugme u meniju izvrši radnju i zatvori meni; izbori
 * (checkbox, select) ostavljaju meni otvoren. Zatvara se klikom van menija i tasterom Esc.
 */
export default function Menu({ label, icon, text, title, align = "left", children }: Props) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<CSSProperties>({});
  const root = useRef<HTMLDivElement>(null);
  // meni se crta preko stranice (position: fixed) ispod dugmeta: traka alata se pomera na uskom
  // prozoru, pa bi meni unutar nje bio odsečen i pomerao bi traku umesto da se otvori
  const toggle = () => {
    const box = root.current?.getBoundingClientRect();
    if (box && !open) {
      setPlace(
        align === "right"
          ? { top: box.bottom + 4, right: Math.max(4, window.innerWidth - box.right) }
          : { top: box.bottom + 4, left: Math.max(4, Math.min(box.left, window.innerWidth - 240)) },
      );
    }
    setOpen((current) => !current);
  };

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  return (
    <div
      className="menu"
      ref={root}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation(); // Esc prvo zatvara meni, tek onda radi u editoru
          setOpen(false);
        }
      }}
    >
      <button type="button" aria-label={label} aria-haspopup="true" aria-expanded={open} title={title} className={open ? "open" : ""} onClick={toggle}>
        {icon}
        <span>{text ?? label}</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div
          className={`menu-panel ${align}`}
          style={place}
          role="group"
          aria-label={label}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("button")) setOpen(false);
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
