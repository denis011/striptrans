import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listBlocks: vi.fn(async () => []),
  listPatches: vi.fn(async (pageId: number) => [{ id: 3, page_id: pageId, url: "/api/patches/3/image", above_text: true }]),
  uploadExportPage: vi.fn(async () => ({})),
}));
const draw = vi.hoisted(() => ({ renderPage: vi.fn(async () => new Blob(["png"])) }));

vi.mock("../api", async (original) => ({ ...(await original<typeof import("../api")>()), ...api }));
vi.mock("./renderPage", () => draw);
vi.mock("../lettering/fonts", () => ({
  loadFontMetrics: vi.fn(async (fonts: Record<string, string>) =>
    Object.fromEntries(Object.keys(fonts).map((key) => [key, { family: key, measure: (t: string) => t.length * 0.6, capRatio: 0.7 }])),
  ),
}));

import { runExport } from "./runExport";

describe("izvoz albuma", () => {
  beforeEach(() => vi.clearAllMocks());

  it("svaka stranica se crta sa svojim zakrpama (ručnim i AI prepravkama)", async () => {
    const fonts = [
      { key: "vc", name: "VC", kind: "dialogue" as const, builtin: false, url: "/f/vc" },
      { key: "sfx", name: "SFX", kind: "sfx" as const, builtin: true, url: "/f/sfx" },
    ];
    const page = { id: 298, position: 96, width: 100, height: 140, cleaned_at: null } as never;

    await runExport({
      exportJob: { id: 5, pages: [{ page_id: 298, position: 96, render: true }] } as never,
      pages: [page],
      series: { id: 1, name: "Ramon", source_lang: "it", target_lang: "sr", dialogue_font: "vc", sfx_font: "sfx" },
      fonts,
      onProgress: () => {},
      cancelled: () => false,
    });

    expect(api.listPatches).toHaveBeenCalledWith(298);
    const options = (draw.renderPage.mock.calls[0] as unknown as [{ patches: { url: string }[] }])[0];
    expect(options.patches.map((patch) => patch.url)).toEqual(["/api/patches/3/image"]);
    expect(api.uploadExportPage).toHaveBeenCalledWith(5, 96, expect.any(Blob));
  });
});
