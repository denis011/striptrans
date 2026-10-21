import { afterEach, describe, expect, it, vi } from "vitest";
import { copyAiPrompt, copyForAi } from "./PatchTools";

class FakeItem {
  constructor(public items: Record<string, Promise<Blob>>) {}
}

describe("ručni AI tok: clipboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  const setup = () => {
    vi.stubGlobal("ClipboardItem", FakeItem);
    vi.stubGlobal("navigator", { clipboard: { write: vi.fn(async () => undefined), writeText: vi.fn(async () => undefined) } });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.includes("ai-prompt") ? Response.json({ prompt: "UPUTSTVO" }) : new Response("png"))));
    vi.stubGlobal("open", vi.fn());
    return navigator.clipboard as unknown as { write: ReturnType<typeof vi.fn>; writeText: ReturnType<typeof vi.fn> };
  };

  it("isečak ide sam (Gemini iz jednog lepljenja uzima samo sliku)", async () => {
    const clipboard = setup();
    const onNote = vi.fn();

    await copyForAi(11, { position: 2 }, { x: 0, y: 0, width: 10, height: 10 }, onNote);

    expect(Object.keys(clipboard.write.mock.calls[0][0][0].items)).toEqual(["image/png"]);
    expect(onNote.mock.calls[0][0]).toMatch(/ponovo G/);
  });

  it("uputstvo se kopira kao tekst", async () => {
    const clipboard = setup();

    await copyAiPrompt(5, vi.fn());

    expect(clipboard.writeText).toHaveBeenCalledWith("UPUTSTVO");
  });
});
