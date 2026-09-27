import { useRef, useState } from "react";

interface Props {
  onFiles: (files: File[]) => void;
  label: string;
  disabled?: boolean;
}

export default function FileDrop({ onFiles, label, disabled = false }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const accept = (list: FileList | null) => {
    if (list && list.length > 0 && !disabled) onFiles(Array.from(list));
  };

  return (
    <div
      className={`dropzone${over ? " over" : ""}${disabled ? " disabled" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => input.current?.click()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") input.current?.click();
      }}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        accept(event.dataTransfer.files);
      }}
    >
      <span>{label}</span>
      <span className="hint">JPG, PNG, CBZ, CBR, ZIP, RAR, 7z, PDF</span>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        data-testid="file-input"
        onChange={(event) => {
          accept(event.target.files);
          event.target.value = "";
        }}
      />
    </div>
  );
}
