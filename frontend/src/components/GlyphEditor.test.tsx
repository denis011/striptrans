import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { TextBlock, TitleGlyph, TitleGlyphs } from "../api";
import GlyphEditor from "./GlyphEditor";

// Konva traži pravi canvas: platna se zamenjuju običnim elementima, a crtanje slova mock-om
vi.mock("react-konva", () => {
  const Box = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return { Stage: Box, Layer: Box, Group: Box, Image: () => null, Line: () => null, Rect: () => null, Transformer: () => null };
});
const renderGlyph = vi.hoisted(() => vi.fn(async () => ({ blob: new Blob(["png"], { type: "image/png" }), baseline: 262 })));
vi.mock("../export/renderGlyph", () => ({ renderGlyph }));

const glyph = (key: string, char: string, source: TitleGlyph["source"] = "original"): TitleGlyph => ({
  key,
  char,
  source,
  width: 180,
  height: 270,
  baseline: 262,
  ink_left: 3,
  ink_right: 177,
});
const title: TitleGlyphs = {
  version: "v1",
  text: "PASSACRO!",
  light: true,
  ink: 255,
  background: 2,
  left: 169,
  top: 157,
  right: 1613,
  bottom: 421,
  cap_height: 256,
  max_scale: 1.3,
  gap: -6,
  word_gap: 80,
  found: 9,
  expected: 9,
  glyphs: [..."PASSACRO!"].map((char, i) => glyph(`g${i}`, char)),
  extra: [glyph("x0", "K", "fallback")],
};
const block = { id: 7, title } as TextBlock;

describe("prozor Novo slovo", () => {
  it("sastavlja slovo od celog R u ogledalu i čuva ga", async () => {
    const onSave = vi.fn(async () => undefined);
    const onClose = vi.fn();
    render(<GlyphEditor block={block} char="K" onSave={onSave} onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: "R" }));
    await userEvent.click(screen.getByRole("button", { name: "Celo slovo" }));
    await userEvent.click(screen.getByRole("button", { name: "Ogledalo levo-desno" }));
    await userEvent.click(screen.getByRole("button", { name: "Sačuvaj slovo" }));

    expect(onSave).toHaveBeenCalledOnce();
    const [image, saved] = onSave.mock.calls[0] as unknown as [Blob, { char: string; baseline: number; parts: { source: string; scaleX: number }[] }];
    expect(image).toBeInstanceOf(Blob);
    expect(saved).toMatchObject({ char: "K", baseline: 262 });
    expect(saved.parts).toEqual([expect.objectContaining({ source: "g6", scaleX: -1 })]);
    expect(onClose).toHaveBeenCalled();
  });

  it("Delete briše izabran deo, Esc zatvara prozor i ne ide do editora stranice", async () => {
    const onClose = vi.fn();
    const onWindowKey = vi.fn();
    window.addEventListener("keydown", onWindowKey);
    render(<GlyphEditor block={block} char="K" onSave={vi.fn()} onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Celo slovo" }));
    expect(screen.getByRole("button", { name: "Sačuvaj slovo" })).toBeEnabled();
    screen.getByRole("dialog").focus();
    await userEvent.keyboard("{Delete}");
    expect(screen.getByRole("button", { name: "Sačuvaj slovo" })).toBeDisabled();
    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
    expect(onWindowKey).not.toHaveBeenCalled();
    window.removeEventListener("keydown", onWindowKey);
  });

  it("uređuje postojeće sastavljeno slovo i nudi brisanje", async () => {
    const editing = { ...glyph("c0", "K", "custom"), parts: [{ source: "g6", polygon: [[0, 0], [9, 0], [9, 9]], x: 10, y: 20, scaleX: 1, scaleY: 1, rotation: 0 }] };
    const onDelete = vi.fn();
    const onSave = vi.fn(async () => undefined);
    render(<GlyphEditor block={{ ...block, title: { ...title, custom: [editing] } }} char="K" editing={editing} onSave={onSave} onDelete={onDelete} onClose={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Uredi slovo" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sačuvaj slovo" }));
    expect((onSave.mock.calls[0] as unknown as [Blob, { key: string }])[1].key).toBe("c0");
    await userEvent.click(screen.getByRole("button", { name: "Obriši slovo" }));
    expect(onDelete).toHaveBeenCalled();
  });
});
