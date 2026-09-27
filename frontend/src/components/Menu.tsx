import { ChevronDown } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

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
  const root = useRef<HTMLDivElement>(null);

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
      <button type="button" aria-label={label} aria-haspopup="true" aria-expanded={open} title={title} className={open ? "open" : ""} onClick={() => setOpen((current) => !current)}>
        {icon}
        <span>{text ?? label}</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div
          className={`menu-panel ${align}`}
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
