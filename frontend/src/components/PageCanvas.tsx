import type Konva from "konva";
import { Fragment, useEffect, useRef, useState } from "react";
import { Group, Image as KonvaImage, Layer, Line, Rect as KonvaRect, Stage, Text, Transformer } from "react-konva";
import type { LetteringStyle, MaskStroke, Patch, PatchChanges, Rect, TextBlock } from "../api";
import type { Lettering } from "../lettering/blocks";
import { emphasizeSelection, isEmphasisKey } from "../lettering/emphasisInput";
import { letteringShapes } from "../lettering/shapes";
import { useImages } from "../viewer/useImages";
import { MIN_BLOCK_SIZE, clampRect, kindColor, rectFromPoints } from "../editor/blocks";
import { useHtmlImage } from "../viewer/useHtmlImage";
import { type Box, type FitMode, type Point, type View, ZOOM_STEP, fitView, screenRect, zoomAt } from "../viewer/zoom";

export interface Fit {
  mode: FitMode;
  /** Menja se na svaki klik, da ponovni izbor istog režima ponovo uklopi stranicu. */
  token: number;
}

interface Props {
  url: string;
  // prikaz (zum, pomeraj) se vraća na početni samo kad se promeni ključ (druga stranica), ne i kad se
  // promeni verzija slike iste stranice (očišćeno / original, potez četkice)
  viewKey?: string | number;
  width: number;
  height: number;
  fit: Fit;
  blocks?: TextBlock[];
  selectedIds?: number[];
  drawMode?: boolean;
  onSelect?: (id: number | null, additive: boolean) => void;
  onChangeBlock?: (id: number, rect: Rect) => void;
  onCreateBlock?: (rect: Rect) => void;
  lettering?: Lettering[];
  editLettering?: boolean; // tekst prevoda se pomera, uvećava i rotira mišem
  onChangeLettering?: (id: number, changes: Partial<LetteringStyle>) => void;
  brush?: { mode: MaskStroke["mode"]; radius: number } | null; // četkica za masku čišćenja
  onBrushStroke?: (stroke: MaskStroke) => void;
  patches?: Patch[]; // zakrpe slikom (Faza 6c)
  editPatches?: boolean; // zakrpa se bira, pomera, uvećava i rotira mišem
  selectedPatchId?: number | null;
  onSelectPatch?: (id: number | null) => void;
  onChangePatch?: (id: number, changes: PatchChanges) => void;
  // izmena prevoda na samoj slici (dvoklik): tekst bloka i snimanje
  blockText?: (id: number) => string;
  onChangeText?: (id: number, text: string) => void;
}

const NO_BLOCKS: TextBlock[] = [];
const NO_SELECTION: number[] = [];
const NO_PATCHES: Patch[] = [];
const MIN_PATCH_SIZE = 4;
const MIN_EDITOR = { width: 160, height: 48 }; // polje za tekst ne sme da bude sitnije od ovoga

const isAdditive = (event: MouseEvent) => event.shiftKey || event.ctrlKey || event.metaKey;

/** Polje za izmenu teksta iznad canvas-a: mesto bloka i izgled složenog teksta. */
interface TextEditor {
  id: number;
  box: Box;
  family?: string;
  size?: number;
  lineHeight?: number;
  align?: "left" | "center" | "right";
  rotation?: number;
}

export default function PageCanvas({
  url,
  viewKey,
  width,
  height,
  fit,
  blocks = NO_BLOCKS,
  selectedIds = NO_SELECTION,
  drawMode = false,
  onSelect,
  onChangeBlock,
  onCreateBlock,
  lettering,
  editLettering = false,
  onChangeLettering,
  brush = null,
  onBrushStroke,
  patches = NO_PATCHES,
  editPatches = false,
  selectedPatchId = null,
  onSelectPatch,
  onChangePatch,
  blockText,
  onChangeText,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const stage = useRef<Konva.Stage>(null);
  const transformer = useRef<Konva.Transformer>(null);
  const letteringTransformer = useRef<Konva.Transformer>(null);
  const letterImages = useImages(lettering?.flatMap((item) => item.images?.map((image) => image.url) ?? []) ?? []);
  const patchTransformer = useRef<Konva.Transformer>(null);
  const patchImages = useImages(patches.map((patch) => patch.url));
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [draft, setDraft] = useState<{ start: Point; end: Point } | null>(null);
  const [stroke, setStroke] = useState<[number, number][] | null>(null);
  const [editing, setEditing] = useState<TextEditor | null>(null);
  const [textDraft, setTextDraft] = useState("");
  const pageKey = viewKey ?? url;
  const { image, failed } = useHtmlImage(url, pageKey);
  const page = { width, height };

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (size.width > 0 && size.height > 0) setView(fitView(size, { width, height }, fit.mode));
  }, [size, width, height, fit, pageKey]);

  useEffect(() => {
    // transformer (ručke za resize) se kači samo kad je izabran tačno jedan blok
    const single = selectedIds.length === 1 && !drawMode;
    const node = single && !editLettering ? stage.current?.findOne(`#block-${selectedIds[0]}`) : undefined;
    transformer.current?.nodes(node ? [node] : []);
    transformer.current?.getLayer()?.batchDraw();
    const text = single && editLettering ? stage.current?.findOne(`#lettering-${selectedIds[0]}`) : undefined;
    letteringTransformer.current?.nodes(text ? [text] : []);
    letteringTransformer.current?.getLayer()?.batchDraw();
  }, [selectedIds, blocks, drawMode, size.width, editLettering, lettering]);

  useEffect(() => {
    const patch = editPatches && selectedPatchId ? stage.current?.findOne(`#patch-${selectedPatchId}`) : undefined;
    patchTransformer.current?.nodes(patch ? [patch] : []);
    patchTransformer.current?.getLayer()?.batchDraw();
  }, [selectedPatchId, patches, editPatches, size.width, patchImages]);

  useEffect(() => {
    setEditing(null);  // druga stranica ili drugi režim: polje za tekst se zatvara bez snimanja
  }, [pageKey, editLettering, drawMode, editPatches]);

  const pointer = (): Point | null => stage.current?.getRelativePointerPosition() ?? null;

  /** Dvoklik na blok ili na složen tekst otvara polje za izmenu prevoda tu gde se tekst i vidi. */
  const openEditor = (editor: TextEditor) => {
    if (!onChangeText || !blockText) return;
    setTextDraft(blockText(editor.id));
    setEditing(editor);
  };
  const closeEditor = (save: boolean) => {
    if (save && editing && textDraft !== blockText?.(editing.id)) onChangeText?.(editing.id, textDraft);
    setEditing(null);
  };
  const editorBox = editing ? screenRect(view, editing.box, MIN_EDITOR) : null;

  const onWheel = (event: Konva.KonvaEventObject<WheelEvent>) => {
    event.evt.preventDefault();
    const position = event.target.getStage()?.getPointerPosition();
    if (!position) return;
    const factor = event.evt.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    setView((current) => zoomAt(current, position, factor));
  };

  const finishDraft = () => {
    if (!draft) return;
    const rect = clampRect(rectFromPoints(draft.start, draft.end), page);
    setDraft(null);
    if (rect.width >= MIN_BLOCK_SIZE && rect.height >= MIN_BLOCK_SIZE) onCreateBlock?.(rect);
  };

  const draftRect = draft ? rectFromPoints(draft.start, draft.end) : null;

  /** Zakrpe se crtaju ispod složenog teksta, a one sa „iznad teksta" preko njega. */
  const patchImage = (patch: Patch) => {
    const element = patchImages.get(patch.url);
    if (!element) return null;
    return (
      <KonvaImage
        key={patch.id}
        id={`patch-${patch.id}`}
        name="patch"
        image={element}
        x={patch.x}
        y={patch.y}
        width={patch.width}
        height={patch.height}
        rotation={patch.rotation}
        opacity={patch.opacity}
        draggable={editPatches}
        listening={editPatches}
        onMouseDown={(event) => {
          event.cancelBubble = true;
          onSelectPatch?.(patch.id);
        }}
        onDragEnd={(event) => {
          event.cancelBubble = true;
          onChangePatch?.(patch.id, { x: event.target.x(), y: event.target.y() });
        }}
        onTransformEnd={(event) => {
          const node = event.target;
          const changes = {
            x: node.x(),
            y: node.y(),
            width: Math.max(MIN_PATCH_SIZE, node.width() * node.scaleX()),
            height: Math.max(MIN_PATCH_SIZE, node.height() * node.scaleY()),
            rotation: Math.round(node.rotation() * 10) / 10,
          };
          node.scaleX(1);
          node.scaleY(1);
          onChangePatch?.(patch.id, changes);
        }}
      />
    );
  };

  return (
    <div ref={container} className={`page-canvas${drawMode || brush ? " drawing" : ""}`}>
      {failed && <p className="error overlay">Slika nije učitana.</p>}
      {size.width > 0 && (
        <Stage
          ref={stage}
          width={size.width}
          height={size.height}
          scaleX={view.scale}
          scaleY={view.scale}
          x={view.x}
          y={view.y}
          draggable={!drawMode && !brush}
          onWheel={onWheel}
          onDragEnd={(event) => {
            const target = event.target;
            if (target === target.getStage()) setView((v) => ({ ...v, x: target.x(), y: target.y() }));
          }}
          onMouseDown={() => {
            const start = drawMode || brush ? pointer() : null;
            if (start && brush) setStroke([[start.x, start.y]]);
            else if (start) setDraft({ start, end: start });
          }}
          onMouseMove={() => {
            const end = draft || stroke ? pointer() : null;
            if (stroke && end) setStroke([...stroke, [end.x, end.y]]);
            else if (draft && end) setDraft({ ...draft, end });
          }}
          onMouseUp={() => {
            if (stroke && brush) {
              onBrushStroke?.({ mode: brush.mode, radius: brush.radius, points: stroke });
              setStroke(null);
              return;
            }
            finishDraft();
          }}
          onClick={(event) => {
            const target = event.target;
            if (drawMode || !(target === target.getStage() || target.name() === "page-image")) return;
            if (editPatches) onSelectPatch?.(null);
            else onSelect?.(null, false);
          }}
        >
          <Layer listening={editPatches}>
            {image && <KonvaImage name="page-image" image={image} width={width} height={height} listening={false} />}
            {patches.filter((patch) => !patch.above_text).map(patchImage)}
          </Layer>
          {lettering && (
            <Layer listening={editLettering}>
              {lettering.map((item) => {
                const { id, layout, style, center } = item;
                const { group, texts, images } = letteringShapes(item);
                return (
                  <Group
                    key={id}
                    id={`lettering-${id}`}
                    name="lettering"
                    {...group}
                    draggable={editLettering}
                    onMouseDown={(event) => {
                      if (!editLettering) return;
                      event.cancelBubble = true;
                      onSelect?.(id, isAdditive(event.evt));
                    }}
                    onDblClick={(event) => {
                      if (!editLettering) return;
                      event.cancelBubble = true;
                      openEditor({
                        id,
                        // tekst je pomeren rukom (dx, dy), pa polje ide tamo gde se tekst vidi
                        box: { x: layout.x + style.dx, y: layout.y + style.dy, width: layout.width, height: layout.height },
                        family: item.family,
                        size: layout.size,
                        lineHeight: layout.lineHeight,
                        align: style.align === "justify" ? "center" : style.align,
                        rotation: style.rotation + (item.tilt ?? 0),
                      });
                    }}
                    onDragEnd={(event) => {
                      event.cancelBubble = true;
                      onChangeLettering?.(id, { dx: event.target.x() - center.x, dy: event.target.y() - center.y });
                    }}
                    onTransformEnd={(event) => {
                      const node = event.target;
                      const scale = style.scale * node.scaleX();
                      node.scaleX(1);
                      node.scaleY(1);
                      onChangeLettering?.(id, {
                        scale: Math.round(Math.min(3, Math.max(0.3, scale)) * 100) / 100,
                        // ugao kosog naslova je iz originala; u stil ide samo ručna rotacija
                        rotation: Math.round(node.rotation() - (item.tilt ?? 0)),
                        dx: node.x() - center.x,
                        dy: node.y() - center.y,
                      });
                    }}
                  >
                    {editLettering && (
                      <KonvaRect x={layout.x} y={layout.y} width={layout.width} height={layout.height} fill="rgba(0,0,0,0.001)" stroke="#2563eb" strokeWidth={1} dash={[6, 4]} strokeScaleEnabled={false} />
                    )}
                    {texts.map((shape, index) => (
                      <Text key={index} {...shape} />
                    ))}
                    {images.map(({ url, ...rect }, index) => {
                      const element = letterImages.get(url);
                      return element ? <KonvaImage key={`letter-${index}`} image={element} {...rect} /> : null;
                    })}
                  </Group>
                );
              })}
              <Transformer
                ref={letteringTransformer}
                rotateEnabled
                keepRatio
                enabledAnchors={["top-left", "top-right", "bottom-left", "bottom-right"]}
                rotationSnaps={[0, 90, 180, 270]}
              />
            </Layer>
          )}
          <Layer>
            {(editLettering ? NO_BLOCKS : blocks).map((block) => {
              const selected = selectedIds.includes(block.id);
              const color = kindColor(block.kind);
              return (
                <Fragment key={block.id}>
                  <KonvaRect
                    id={`block-${block.id}`}
                    x={block.x}
                    y={block.y}
                    width={block.width}
                    height={block.height}
                    stroke={color}
                    strokeWidth={selected ? 3 : 2}
                    strokeScaleEnabled={false}
                    fill={selected ? `${color}33` : `${color}12`}
                    draggable={selected && !drawMode}
                    listening={!drawMode}
                    onClick={(event) => {
                      event.cancelBubble = true;
                      onSelect?.(block.id, isAdditive(event.evt));
                    }}
                    onDblClick={(event) => {
                      event.cancelBubble = true;
                      openEditor({ id: block.id, box: { x: block.x, y: block.y, width: block.width, height: block.height } });
                    }}
                    onDragEnd={(event) => {
                      event.cancelBubble = true;
                      const node = event.target;
                      const moved = { x: node.x(), y: node.y(), width: block.width, height: block.height };
                      onChangeBlock?.(block.id, clampRect(moved, page));
                    }}
                    onTransformEnd={(event) => {
                      const node = event.target;
                      const resized = {
                        x: node.x(),
                        y: node.y(),
                        width: Math.max(MIN_BLOCK_SIZE, node.width() * node.scaleX()),
                        height: Math.max(MIN_BLOCK_SIZE, node.height() * node.scaleY()),
                      };
                      node.scaleX(1);
                      node.scaleY(1);
                      onChangeBlock?.(block.id, clampRect(resized, page));
                    }}
                  />
                  <Text
                    x={block.x}
                    y={block.y - 20 / view.scale}
                    text={String(block.position)}
                    fontSize={16 / view.scale}
                    fontStyle="bold"
                    fill={color}
                    listening={false}
                  />
                </Fragment>
              );
            })}
            {draftRect && (
              <KonvaRect {...draftRect} stroke="#1d4ed8" dash={[6, 4]} strokeWidth={2} strokeScaleEnabled={false} listening={false} />
            )}
            <Transformer ref={transformer} rotateEnabled={false} flipEnabled={false} keepRatio={false} ignoreStroke />
          </Layer>
          <Layer listening={editPatches}>
            {patches.filter((patch) => patch.above_text).map(patchImage)}
            <Transformer ref={patchTransformer} rotateEnabled keepRatio={false} rotationSnaps={[0, 90, 180, 270]} />
          </Layer>
          {stroke && brush && (
            <Layer listening={false}>
              <Line
                points={stroke.flat()}
                stroke={brush.mode === "add" || brush.mode === "patch-hide" ? "rgba(220,38,38,0.45)" : "rgba(37,99,235,0.45)"}
                strokeWidth={brush.radius * 2}
                lineCap="round"
                lineJoin="round"
              />
            </Layer>
          )}
        </Stage>
      )}
      {editing && editorBox && (
        <textarea
          className="block-editor"
          aria-label="Tekst na slici"
          autoFocus
          value={textDraft}
          spellCheck={false}
          style={{
            left: editorBox.x,
            top: editorBox.y,
            width: editorBox.width,
            height: editorBox.height,
            fontFamily: editing.family || undefined,
            fontSize: editing.size ? editing.size * view.scale : undefined,
            lineHeight: editing.lineHeight ?? undefined,
            textAlign: editing.align ?? "center",
            transform: editing.rotation ? `rotate(${editing.rotation}deg)` : undefined,
          }}
          onChange={(event) => setTextDraft(event.target.value)}
          onBlur={() => closeEditor(true)}
          onKeyDown={(event) => {
            event.stopPropagation();  // prečice editora ne rade dok se kuca
            if (event.key === "Escape") {
              event.preventDefault();
              setEditing(null);  // odustajanje: tekst ostaje kakav je bio
            } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              closeEditor(true);
            } else if (isEmphasisKey(event)) {
              event.preventDefault();
              emphasizeSelection(event.currentTarget, setTextDraft);
            }
          }}
        />
      )}
    </div>
  );
}
