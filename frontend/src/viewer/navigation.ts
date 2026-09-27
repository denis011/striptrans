/** Nova pozicija stranice (1..count) za pritisnut taster, ili null ako taster ne menja stranicu. */
export function positionForKey(key: string, current: number, count: number): number | null {
  const target =
    key === "ArrowRight" || key === "PageDown"
      ? current + 1
      : key === "ArrowLeft" || key === "PageUp"
        ? current - 1
        : key === "Home"
          ? 1
          : key === "End"
            ? count
            : null;
  if (target === null || target < 1 || target > count || target === current) return null;
  return target;
}

/** Premesti stavku `moved` na mesto stavke `target`. */
export function moveItem(ids: number[], moved: number, target: number): number[] {
  const from = ids.indexOf(moved);
  const to = ids.indexOf(target);
  if (from === -1 || to === -1 || from === to) return ids;
  const result = [...ids];
  result.splice(from, 1);
  result.splice(to, 0, moved);
  return result;
}

/** Pomeraj izabranog bloka ili zakrpe strelicom: 1 px stranice, sa Shift-om 10 px. */
export function nudgeForKey(key: string, shift: boolean): [number, number] | null {
  const step = shift ? 10 : 1;
  const delta: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0],
    ArrowRight: [step, 0],
    ArrowUp: [0, -step],
    ArrowDown: [0, step],
  };
  return delta[key] ?? null;
}
