import type { Patch } from "../api";

/** Tačka stranice u koordinatama zakrpe (pomerena i rotirana oko gornjeg levog ugla, kao u Konvi). */
export function toPatch(patch: Patch, x: number, y: number): [number, number] {
  const angle = (patch.rotation * Math.PI) / 180;
  const dx = x - patch.x;
  const dy = y - patch.y;
  return [dx * Math.cos(angle) + dy * Math.sin(angle), -dx * Math.sin(angle) + dy * Math.cos(angle)];
}

/** Najgornja zakrpa na tački stranice: one „iznad teksta" se crtaju poslednje, pa su na vrhu. */
export function patchAt(patches: Patch[], x: number, y: number): Patch | null {
  const order = [...patches].sort((a, b) => Number(b.above_text) - Number(a.above_text) || b.position - a.position);
  return (
    order.find((patch) => {
      const [u, v] = toPatch(patch, x, y);
      return u >= 0 && v >= 0 && u <= patch.width && v <= patch.height;
    }) ?? null
  );
}
