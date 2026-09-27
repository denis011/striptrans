import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useHtmlImage } from "./useHtmlImage";

// jsdom ne učitava slike: lažna slika javlja onload tek kad test to zatraži
const pending: FakeImage[] = [];
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  src = "";
  constructor() {
    pending.push(this);
  }
}

function loadAll() {
  act(() => {
    for (const image of pending.splice(0)) image.onload?.();
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  pending.length = 0;
});

describe("useHtmlImage", () => {
  it("dok se učitava nova verzija iste stranice, zadržava staru sliku", () => {
    vi.stubGlobal("Image", FakeImage);
    const { result, rerender } = renderHook(({ url, key }) => useHtmlImage(url, key), {
      initialProps: { url: "/api/pages/1/clean-image?v=1", key: 1 },
    });
    loadAll();
    const first = result.current.image;
    expect(first).not.toBeNull();

    rerender({ url: "/api/pages/1/clean-image?v=2", key: 1 });
    expect(result.current.image).toBe(first); // nema treptanja

    loadAll();
    expect(result.current.image).not.toBe(first);
  });

  it("za drugu stranicu ne prikazuje staru sliku", () => {
    vi.stubGlobal("Image", FakeImage);
    const { result, rerender } = renderHook(({ url, key }) => useHtmlImage(url, key), {
      initialProps: { url: "/api/pages/1/image", key: 1 },
    });
    loadAll();

    rerender({ url: "/api/pages/2/image", key: 2 });

    expect(result.current.image).toBeNull();
  });
});
