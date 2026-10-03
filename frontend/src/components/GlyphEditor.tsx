import type Konva from "konva";
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Image as KonvaImage, Layer, Line, Rect, Stage, Transformer } from "react-konva";
import { type GlyphPart, type TextBlock, type TitleGlyph, titleGlyphUrl } from "../api";
import { renderGlyph } from "../export/renderGlyph";
import { type Point, addPoint, cutPart, glyphCanvas, isArea, mirrored, newPart, partPlacement, rectPolygon, toSource, wholeGlyph } from "../lettering/glyphParts";
import { choicesFor } from "../lettering/title";
import { useImages } from "../viewer/useImages";

const SOURCE_SIZE = 460; // px, prikaz izvornog slova (pre zumiranja)
const CANVAS_HEIGHT = 440; // px, prikaz novog slova
const SOURCE_ZOOMS = [1, 1.5, 2, 3]; // uvećanje izvornog slova za precizan izrez slobodnom rukom
const BOARD = 140; // px praznog prostora oko originala: prikaz se pomera u svim pravcima, i kad je slovo usko
const PAN_STEP = 40; // px pomeranja prikaza strelicom (sa Shift-om tri puta više)
type RightTool = "move" | "erase-rect" | "erase-lasso" | "erase-brush";

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
  const [sourceZoom, setSourceZoom] = useState(1);
  const [rightTool, setRightTool] = useState<RightTool>("move");
  const [brush, setBrush] = useState(8); // px na ekranu, poluprečnik gumice
  const [draft, setDraft] = useState<number[][]>([]); // potez brisanja u toku (tačke platna)
  const [drawing, setDrawing] = useState(false);
  const history = useRef<GlyphPart[][]>([]); // Poništi u prozoru (dodavanje, brisanje, izmene delova)
  // pomeranje uvećanog originala kao u Photoshopu: Space + prevlačenje levim tasterom
  const [space, setSpace] = useState(false);
  const [panning, setPanning] = useState(false);
  const view = useRef<HTMLDivElement>(null);
  const pan = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
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
    const key = `${fill ? "f" : ""}${part.source}|${JSON.stringify(part.polygon)}|${JSON.stringify(part.erase ?? [])}`;
    if (!cuts.current.has(key)) cuts.current.set(key, cutPart(image, part.polygon, part.erase));
    return cuts.current.get(key) ?? undefined;
  };
  const source = sources.find((glyph) => glyph.key === sourceKey);
  const sourceScale = (source ? Math.min(SOURCE_SIZE / source.width, SOURCE_SIZE / source.height) : 1) * sourceZoom;
  const zoom = CANVAS_HEIGHT / canvas.height;
  const background = title.light ? "#111" : "#fff";
  // bledo slovo u pozadini (napravljeno ili iz originala) pomaže da se delovi poravnaju
  const guide = choicesFor(title, char.toUpperCase()).find((glyph) => glyph.key !== editing?.key);

  useEffect(() => root.current?.focus(), []);
  // posle promene slova ili uvećanja original je na sredini prikaza
  useEffect(() => {
    const element = view.current;
    if (!element) return;
    element.scrollLeft = (element.scrollWidth - element.clientWidth) / 2;
    element.scrollTop = (element.scrollHeight - element.clientHeight) / 2;
  }, [sourceKey, sourceZoom]);
  const panBy = (dx: number, dy: number) => view.current?.scrollBy({ left: dx, top: dy });
  const zoomStep = (direction: 1 | -1) =>
    setSourceZoom((value) => SOURCE_ZOOMS[Math.min(SOURCE_ZOOMS.length - 1, Math.max(0, SOURCE_ZOOMS.indexOf(value) + direction))]);
  useEffect(() => {
    if (!panning) return;
    const move = (event: MouseEvent) => {
      const start = pan.current;
      if (!start || !view.current) return;
      view.current.scrollLeft = start.left - (event.clientX - start.x);
      view.current.scrollTop = start.top - (event.clientY - start.y);
    };
    const up = () => {
      pan.current = null;
      setPanning(false);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [panning]);
  useEffect(() => {
    const node = current === null || rightTool !== "move" ? undefined : stage.current?.findOne(`#part-${current}`);
    transformer.current?.nodes(node ? [node] : []);
    transformer.current?.getLayer()?.batchDraw();
  }, [current, parts, rightTool]);

  const remember = () => {
    history.current = [...history.current.slice(-49), parts];
  };
  const undo = () => {
    const previous = history.current.pop();
    if (!previous) return;
    setParts(previous);
    setCurrent((index) => (index !== null && index < previous.length ? index : null));
  };
  const update = (index: number, changes: Partial<GlyphPart>) => {
    remember();
    setParts((list) => list.map((part, i) => (i === index ? { ...part, ...changes } : part)));
  };
  const addPart = (polygon: number[][]) => {
    if (!source) return;
    remember();
    setParts((list) => [...list, newPart(source, polygon, canvas)]);
    setCurrent(parts.length);
    setSelection([]);
  };
  const removePart = () => {
    if (current === null) return;
    remember();
    setParts((list) => list.filter((_, i) => i !== current));
    setCurrent(null);
  };
  // brisanje dela izreza na desnoj strani: potez u tačkama platna → pikseli izvornog slova dela
  const canvasPoint = (event: Konva.KonvaEventObject<MouseEvent>): Point => event.target.getStage()?.getRelativePointerPosition() ?? { x: 0, y: 0 };
  const finishErase = () => {
    setDrawing(false);
    const points = draft;
    setDraft([]);
    if (current === null || points.length === 0) return;
    const part = parts[current];
    const cut =
      rightTool === "erase-brush"
        ? { points: points.map(([x, y]) => toSource(part, { x, y })).map(({ x, y }) => [x, y]), radius: brush / (zoom * ((Math.abs(part.scaleX) + Math.abs(part.scaleY)) / 2)) }
        : isArea(points)
          ? { points: points.map(([x, y]) => toSource(part, { x, y })).map(({ x, y }) => [x, y]) }
          : null;
    if (cut) update(current, { erase: [...(part.erase ?? []), cut] });
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
        onKeyUp={(event) => {
          if (event.key === " ") {
            event.preventDefault();
            setSpace(false);
          }
        }}
        onKeyDown={(event) => {
          event.stopPropagation(); // prečice editora stranice ne važe u prozoru
          const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement;
          const arrows: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
          if (arrows[event.key] && !typing) {
            event.preventDefault();
            const step = PAN_STEP * (event.shiftKey ? 3 : 1);
            panBy(arrows[event.key][0] * step, arrows[event.key][1] * step);
          }
          if ((event.key === "+" || event.key === "=") && !typing) zoomStep(1);
          if (event.key === "-" && !typing) zoomStep(-1);
          if (event.key === " " && !typing) {
            event.preventDefault(); // Space ne „klikne" dugme i ne skroluje prozor
            setSpace(true);
          }
          if (event.key === "Escape") onClose();
          if ((event.key === "Delete" || event.key === "Backspace") && !typing) removePart();
          if (event.key.toLowerCase() === "z" && (event.ctrlKey || event.metaKey) && !typing) {
            event.preventDefault();
            undo();
          }
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
            <div className="toolbar-group">
              <div className="segmented">
                <button type="button" className={tool === "rect" ? "active" : ""} aria-pressed={tool === "rect"} onClick={() => setTool("rect")}>
                  Pravougaonik
                </button>
                <button type="button" className={tool === "lasso" ? "active" : ""} aria-pressed={tool === "lasso"} onClick={() => setTool("lasso")}>
                  Slobodno
                </button>
              </div>
              <label className="detail">
                Uvećanje{" "}
                <select aria-label="Uvećanje originala" value={sourceZoom} onChange={(event) => setSourceZoom(Number(event.target.value))}>
                  {SOURCE_ZOOMS.map((value) => (
                    <option key={value} value={value}>
                      {value * 100} %
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {source && (
              <div
                className={`glyph-source-view${space ? " panning" : ""}${panning ? " grabbing" : ""}`}
                ref={view}
                onMouseDownCapture={(event) => {
                  if (!space || event.button !== 0 || !view.current) return;
                  event.stopPropagation(); // dok je Space pritisnut, prevlačenje pomera prikaz umesto izreza
                  event.preventDefault();
                  pan.current = { x: event.clientX, y: event.clientY, left: view.current.scrollLeft, top: view.current.scrollTop };
                  setPanning(true);
                }}
              >
              <div className="glyph-source-board" style={{ padding: BOARD }}>
              <Stage
                className="glyph-stage"
                width={source.width * sourceScale}
                height={source.height * sourceScale}
                onMouseDown={(event) => {
                  if (space) return;
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
                <Layer imageSmoothingEnabled={false}>
                  {/* oštri pikseli pri uvećanju: ivice slova se jasno vide za precizan izrez */}
                  <Rect width={source.width * sourceScale} height={source.height * sourceScale} fill={background} />
                  {imageOf(source.key) && <KonvaImage image={imageOf(source.key)} scaleX={sourceScale} scaleY={sourceScale} />}
                  {selection.length > 1 && (
                    <Line points={selection.flat().map((value) => value * sourceScale)} closed stroke="#f59e0b" strokeWidth={2} dash={[6, 4]} fill="rgba(245, 158, 11, 0.2)" />
                  )}
                </Layer>
              </Stage>
              </div>
              </div>
            )}
            <div className="toolbar-group">
              <button type="button" disabled={!isArea(selection)} onClick={() => addPart(selection)}>
                Dodaj deo
              </button>
              <button type="button" disabled={!source} onClick={() => source && addPart(wholeGlyph(source))}>
                Celo slovo
              </button>
            </div>
            <p className="hint">
              Prevuci preko dela slova ({tool === "rect" ? "pravougaonik" : "slobodna linija"}), pa „Dodaj deo".
            </p>
            <dl className="glyph-keys" aria-label="Prečice u prozoru">
              <dt>Space + levi taster</dt>
              <dd>pomeranje originala u svim pravcima</dd>
              <dt>strelice (Shift: brže)</dt>
              <dd>pomeranje originala</dd>
              <dt>točkić / Shift + točkić</dt>
              <dd>gore-dole / levo-desno</dd>
              <dt>+ / −</dt>
              <dd>uvećanje originala</dd>
              <dt>Ctrl+Z · Delete · Esc</dt>
              <dd>poništi · obriši izabrani deo · zatvori</dd>
            </dl>
          </section>
          <section aria-label="Sastavljeno slovo">
            <h3>2. Složi delove</h3>
            <div className="segmented" role="group" aria-label="Alat za delove">
              {(
                [
                  ["move", "Pomeri"],
                  ["erase-rect", "Obriši pravougaonikom"],
                  ["erase-lasso", "Obriši slobodno"],
                  ["erase-brush", "Gumica"],
                ] as const
              ).map(([value, name]) => (
                <button key={value} type="button" className={rightTool === value ? "active" : ""} aria-pressed={rightTool === value} onClick={() => setRightTool(value)}>
                  {name}
                </button>
              ))}
            </div>
            {rightTool === "erase-brush" && (
              <label className="detail">
                Veličina gumice <input type="range" aria-label="Veličina gumice" min={2} max={40} value={brush} onChange={(event) => setBrush(Number(event.target.value))} />
              </label>
            )}
            <Stage
              ref={stage}
              className={`glyph-stage${rightTool === "move" ? "" : " erasing"}`}
              width={canvas.width * zoom}
              height={canvas.height * zoom}
              scaleX={zoom}
              scaleY={zoom}
              onMouseDown={(event) => {
                if (rightTool === "move") {
                  if (event.target === event.target.getStage()) setCurrent(null);
                  return;
                }
                if (current === null) {
                  setError("Prvo izaberi deo koji brišeš (alat „Pomeri“, klik na deo).");
                  return;
                }
                setError(null);
                const point = canvasPoint(event);
                setDrawing(true);
                setDraft(rightTool === "erase-rect" ? rectPolygon(point, point) : [[point.x, point.y]]);
              }}
              onMouseMove={(event) => {
                if (!drawing) return;
                const point = canvasPoint(event);
                setDraft((points) =>
                  rightTool === "erase-rect" ? rectPolygon({ x: points[0][0], y: points[0][1] }, point) : addPoint(points, point, 1 / zoom),
                );
              }}
              onMouseUp={() => drawing && finishErase()}
              onMouseLeave={() => drawing && finishErase()}
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
                      draggable={rightTool === "move"}
                      onMouseDown={() => rightTool === "move" && setCurrent(index)}
                      onDragStart={remember}
                      onDragMove={(event) => setParts((list) => list.map((part, i) => (i === index ? { ...part, x: event.target.x(), y: event.target.y() } : part)))}
                      onDragEnd={(event) => setParts((list) => list.map((part, i) => (i === index ? { ...part, x: event.target.x(), y: event.target.y() } : part)))}
                      onTransformEnd={(event) => {
                        const node = event.target;
                        update(index, { x: node.x(), y: node.y(), scaleX: node.scaleX(), scaleY: node.scaleY(), rotation: node.rotation() });
                      }}
                    />
                  ) : null;
                })}
                {draft.length > 0 &&
                  (rightTool === "erase-brush" ? (
                    <Line points={draft.flat()} stroke="rgba(220, 38, 38, 0.5)" strokeWidth={(brush * 2) / zoom} lineCap="round" lineJoin="round" listening={false} />
                  ) : (
                    <Line points={draft.flat()} closed stroke="#dc2626" strokeWidth={1.5} strokeScaleEnabled={false} dash={[6, 4]} fill="rgba(220, 38, 38, 0.2)" listening={false} />
                  ))}
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
              <button type="button" aria-label="Poništi u prozoru" title="Poništi poslednju izmenu delova (Ctrl+Z)" onClick={undo}>
                ↶ Poništi
              </button>
            </div>
            <p className="hint">
              „Pomeri": deo se pomera prevlačenjem, ugaone ručke menjaju veličinu, a ručka iznad rotira. Alati za brisanje brišu samo
              izabrani deo (izaberi ga u alatu „Pomeri"). Isprekidane linije su osnovna linija i visina slova.
            </p>
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
