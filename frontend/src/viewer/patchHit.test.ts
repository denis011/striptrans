import { describe, expect, it } from "vitest";
import type { Patch } from "../api";
import { patchAt } from "./patchHit";

const patch = (fields: Partial<Patch>): Patch => ({
  id: 1,
  position: 1,
  x: 100,
  y: 100,
  width: 80,
  height: 60,
  rotation: 0,
  opacity: 1,
  above_text: false,
  url: "/api/patches/1/image",
  ...fields,
});

describe("patchAt", () => {
  it("bira najgornju zakrpu na tački", () => {
    const below = patch({ id: 1, position: 2 });
    const above = patch({ id: 2, position: 1, above_text: true });
    const top = patch({ id: 3, position: 3 });
    expect(patchAt([below, top], 120, 120)?.id).toBe(3);
    expect(patchAt([below, top, above], 120, 120)?.id).toBe(2);
    expect(patchAt([below], 50, 50)).toBeNull();
  });

  it("prati rotaciju zakrpe", () => {
    const turned = patch({ rotation: 90 }); // okrenuta oko gornjeg levog ugla: zauzima x 40–100
    expect(patchAt([turned], 70, 120)?.id).toBe(1);
    expect(patchAt([turned], 120, 120)).toBeNull();
  });
});
