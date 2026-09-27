import type Konva from "konva";
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Image as KonvaImage, Layer, Line, Rect, Stage, Transformer } from "react-konva";
import { type GlyphPart, type TextBlock, type TitleGlyph, titleGlyphUrl } from "../api";
import { renderGlyph } from "../export/renderGlyph";
import { type Point, addPoint, cutPart, glyphCanvas, isArea, mirrored, newPart, partPlacement, rectPolygon, wholeGlyph } from "../lettering/glyphParts";
import { choicesFor } from "../lettering/title";
import { useImages } from "../viewer/useImages";

const SOURCE_SIZE = 240; // px, prikaz izvornog slova
const CANVAS_HEIGHT = 340; // px, prikaz novog slova

export interface SavedGlyph {
  char: string;
  baseline: number;
  parts: GlyphPart[];
  key?: string;
}

interface Props {
  block: TextBlock; // naslov sa isečenim slovima
  char: string; // slovo koje se pravi (npr. K)
  editing?: TitleGlyph; // postojeće sastavljeno slovo
  onSave: (image: Blob, glyph: SavedGlyph, fill?: Blob) => Promise<unknown>;
  onDelete?: () => void;
  onClose: () => void;
}

/**
 * Prozor „Novo slovo" (Faza 6b): iz slova originala se mišem izreže deo (pravougaonik ili
 * slobodna linija), deo se prenese na novo slovo i tamo pomera, uvećava, rotira i okreće.
 */
export default function GlyphEditor({ block, char: initialChar, editing, onSave, onDelete, onClose }: Props) {
  const title = block.title!;
  const canvas = glyphCanvas(title);
  const sources = title.glyphs;
  const [char, setChar] = useState(editing?.char ?? initialChar);
  const [sourceKey, setSourceKey] = useState(editing?.parts?.[0]?.source ?? sources[0]?.key ?? "");
  const [tool, setTool] = useState<"rect" | "lasso">("rect");
  const [selection, setSelection] = useState<number[][]>([]);
  const [start, setStart] = useState<Point | null>(null);
  const [parts, setParts] = useState<GlyphPart[]>(editing?.parts ?? []);
  const [current, setCurrent] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<Konva.Stage>(null);
  const transformer = useRef<Konva.Transformer>(null);

  const all = [...title.glyphs, ...(title.custom ?? []), ...title.extra];
  const urls = new Map(all.map((glyph) => [glyph.key, titleGlyphUrl(block.id, title, glyph.key)]));
  // ispune šupljih slova (unutrašnjost boje papira) se seku istim izrezom kao slovo
  const fillUrls = new Map(all.filter((glyph) => glyph.fill).map((glyph) => [glyph.key, titleGlyphUrl(block.id, title, `${glyph.key}f`)]));
  const loaded = useImages([...urls.values(), ...fillUrls.values()]);
  const imageOf = (key: string) => loaded.get(urls.get(key) ?? "");
  const fillOf = (key: string) => loaded.get(fillUrls.get(key) ?? "");
  // izrezi se prave jednom po delu (isti izvor i poligon), kad se slika izvornog slova učita
  const cuts = useRef(new Map<string, HTMLCanvasElement | null>());
  const cutOf = (part: GlyphPart, fill = false) => {
    const image = fill ? fillOf(part.source) : imageOf(part.source);
    if (!image) return undefined;
    const key = `${fill ? "f" : ""}${part.source}|${JSON.stringify(part.polygon)}`;
    if (!cuts.current.has(key)) cuts.current.set(key, cutPart(image, part.polygon));
    return cuts.current.get(key) ?? undefined;
  };
  const source = sources.find((glyph) => glyph.key === sourceKey);
  const sourceScale = source ? Math.min(SOURCE_SIZE / source.width, SOURCE_SIZE / source.height) : 1;
  const zoom = CANVAS_HEIGHT / canvas.height;
  const background = title.light ? "#111" : "#fff";
  // bledo slovo u pozadini (napravljeno ili iz originala) pomaže da se delovi poravnaju
  const guide = choicesFor(title, char.toUpperCase()).find((glyph) => glyph.key !== editing?.key);

  useEffect(() => root.current?.focus(), []);
  useEffect(() => {
    const node = current === null ? undefined : stage.current?.findOne(`#part-${current}`);
    transformer.current?.nodes(node ? [node] : []);
    transformer.current?.getLayer()?.batchDraw();
  }, [current, parts]);

  const update = (index: number, changes: Partial<GlyphPart>) =>
    setParts((list) => list.map((part, i) => (i === index ? { ...part, ...changes } : part)));
  const addPart = (polygon: number[][]) => {
    if (!source) return;
    setParts((list) => [...list, newPart(source, polygon, canvas)]);
    setCurrent(parts.length);
    setSelection([]);
  };
  const removePart = () => {
    if (current === null) return;
    setParts((list) => list.filter((_, i) => i !== current));
    setCurrent(null);
  };
  const pointer = (event: Konva.KonvaEventObject<MouseEvent>): Point => {
    const position = event.target.getStage()?.getPointerPosition() ?? { x: 0, y: 0 };
    return { x: position.x / sourceScale, y: position.y / sourceScale };
  };
  const save = async () => {
    const images = new Map(parts.flatMap((part) => (imageOf(part.source) ? [[part.source, imageOf(part.source)!] as const] : [])));
    const fills = new Map(parts.flatMap((part) => (fillOf(part.source) ? [[part.source, fillOf(part.source)!] as const] : [])));
    setSaving(true);
    setError(null);
    try {
      const rendered = await renderGlyph(parts, images, canvas, fills);
      if (!rendered) throw new Error("slovo je prazno");
      await onSave(rendered.blob, { char: char.trim().toUpperCase(), baseline: rendered.baseline, parts, key: editing?.key }, rendered.fill);
      onClose();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSaving(false);
    }
  };

  const stop = (event: React.SyntheticEvent) => event.stopPropagation();
  return createPortal(
    <div className="modal-backdrop" onClick={stop} onMouseDown={stop}>
      <div
        className="glyph-editor"
        role="dialog"
        aria-modal="true"
        aria-label={editing ? "Uredi slovo" : "Novo slovo"}
        tabIndex={-1}
        ref={root}
        onKeyDown={(event) => {
          event.stopPropagation(); // prečice editora stranice ne važe u prozoru
          const typing = event.target instanceof HTMLInputElement;
          if (event.key === "Escape") onClose();
          if ((event.key === "Delete" || event.key === "Backspace") && !typing) removePart();
        }}
      >
        <header>
          <h2>{editing ? "Uredi slovo" : "Novo slovo"}</h2>
          <label>
            Slovo
            <input aria-label="Slovo" className="glyph-char" maxLength={1} value={char} onChange={(event) => setChar(event.target.value.toUpperCase())} />
          </label>
          <span className="spacer" />
          <button type="button" className="icon-button" aria-label="Zatvori" onClick={onClose}>
            <X size={18} aria-hidden />
          </button>
        </header>
        <div className="glyph-editor-body">
          <section aria-label="Delovi originala">
            <h3>1. Izreži deo slova originala</h3>
            <div className="title-letters" role="group" aria-label="Izvorno slovo">
              {sources.map((glyph) => (
                <button
                  key={glyph.key}
                  type="button"
                  className={`title-letter${glyph.key === sourceKey ? " active" : ""}`}
                  aria-pressed={glyph.key === sourceKey}
                  title={glyph.char}
                  onClick={() => {
                    setSourceKey(glyph.key);
                    setSelection([]);
                  }}
                >
                  <img src={urls.get(glyph.key)} alt={glyph.char} />
                </button>
              ))}
            </div>
            <div className="segmented">
              <button type="button" className={tool === "rect" ? "active" : ""} aria-pressed={tool === "rect"} onClick={() => setTool("rect")}>
                Pravougaonik
              </button>
              <button type="button" className={tool === "lasso" ? "active" : ""} aria-pressed={tool === "lasso"} onClick={() => setTool("lasso")}>
                Slobodno
              </button>
            </div>
            {source && (
              <Stage
                className="glyph-stage"
                width={source.width * sourceScale}
                height={source.height * sourceScale}
                onMouseDown={(event) => {
                  const point = pointer(event);
                  setStart(point);
                  setSelection(tool === "rect" ? rectPolygon(point, point) : [[point.x, point.y]]);
                }}
                onMouseMove={(event) => {
                  if (!start) return;
                  const point = pointer(event);
                  setSelection((points) => (tool === "rect" ? rectPolygon(start, point) : addPoint(points, point)));
                }}
                onMouseUp={() => setStart(null)}
              >
                <Layer>
                  <Rect width={source.width * sourceScale} height={source.height * sourceScale} fill={background} />
                  {imageOf(source.key) && <KonvaImage image={imageOf(source.key)} scaleX={sourceScale} scaleY={sourceScale} />}
                  {selection.length > 1 && (
                    <Line points={selection.flat().map((value) => value * sourceScale)} closed stroke="#f59e0b" strokeWidth={2} dash={[6, 4]} fill="rgba(245, 158, 11, 0.2)" />
                  )}
                </Layer>
              </Stage>
            )}
            <div className="toolbar-group">
              <button type="button" disabled={!isArea(selection)} onClick={() => addPart(selection)}>
                Dodaj deo
              </button>
              <button type="button" disabled={!source} onClick={() => source && addPart(wholeGlyph(source))}>
                Celo slovo
              </button>
            </div>
            <p className="hint">Prevuci preko dela slova ({tool === "rect" ? "pravougaonik" : "slobodna linija"}), pa „Dodaj deo".</p>
          </section>
          <section aria-label="Sastavljeno slovo">
            <h3>2. Složi delove</h3>
            <Stage
              ref={stage}
              className="glyph-stage"
              width={canvas.width * zoom}
              height={canvas.height * zoom}
              scaleX={zoom}
              scaleY={zoom}
              onMouseDown={(event) => event.target === event.target.getStage() && setCurrent(null)}
            >
              <Layer>
                <Rect width={canvas.width} height={canvas.height} fill={background} listening={false} />
                {guide && imageOf(guide.key) && (
                  <KonvaImage
                    image={imageOf(guide.key)}
                    x={canvas.width / 2 - (guide.ink_left + guide.ink_right) / 2}
                    y={canvas.baseline - guide.baseline}
                    opacity={0.18}
                    listening={false}
                  />
                )}
                <Line points={[0, canvas.baseline, canvas.width, canvas.baseline]} stroke="#3b82f6" strokeWidth={1} dash={[8, 6]} strokeScaleEnabled={false} listening={false} />
                <Line points={[0, canvas.baseline - title.cap_height, canvas.width, canvas.baseline - title.cap_height]} stroke="#3b82f6" strokeWidth={1} dash={[8, 6]} strokeScaleEnabled={false} listening={false} />
                {parts.map((part, index) => {
                  // ispuna ispod svih kontura, kao u slaganju naslova
                  const image = cutOf(part, true);
                  return image ? <KonvaImage key={`fill-${index}`} image={image} {...partPlacement(part)} listening={false} /> : null;
                })}
                {parts.map((part, index) => {
                  const image = cutOf(part);
                  return image ? (
                    <KonvaImage
                      key={index}
                      id={`part-${index}`}
                      image={image}
                      {...partPlacement(part)}
                      draggable
                      onMouseDown={() => setCurrent(index)}
                      onDragMove={(event) => update(index, { x: event.target.x(), y: event.target.y() })}
                      onDragEnd={(event) => update(index, { x: event.target.x(), y: event.target.y() })}
                      onTransformEnd={(event) => {
                        const node = event.target;
                        update(index, { x: node.x(), y: node.y(), scaleX: node.scaleX(), scaleY: node.scaleY(), rotation: node.rotation() });
                      }}
                    />
                  ) : null;
                })}
                <Transformer ref={transformer} rotateEnabled keepRatio={false} flipEnabled={false} />
              </Layer>
            </Stage>
            <div className="toolbar-group">
              <button type="button" disabled={current === null} aria-label="Ogledalo levo-desno" onClick={() => current !== null && setParts((list) => list.map((part, i) => (i === current ? mirrored(part, "x") : part)))}>
                ⇆ Ogledalo
              </button>
              <button type="button" disabled={current === null} aria-label="Ogledalo gore-dole" onClick={() => current !== null && setParts((list) => list.map((part, i) => (i === current ? mirrored(part, "y") : part)))}>
                ⇅ Ogledalo
              </button>
              <button type="button" disabled={current === null} onClick={removePart}>
                Obriši deo
              </button>
            </div>
            <p className="hint">Deo se pomera prevlačenjem, ugaone ručke menjaju veličinu, a ručka iznad rotira. Isprekidane linije su osnovna linija i visina slova.</p>
          </section>
        </div>
        <footer>
          {error && <span className="error">{error}</span>}
          {editing && onDelete && (
            <button type="button" className="danger" onClick={onDelete}>
              Obriši slovo
            </button>
          )}
          <span className="spacer" />
          <button type="button" onClick={onClose}>
            Otkaži
          </button>
          <button type="button" className="active" disabled={!parts.length || !char.trim() || saving} onClick={save}>
            {saving ? "Čuvam…" : "Sačuvaj slovo"}
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
