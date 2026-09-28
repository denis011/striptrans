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

const CROP_MARGIN = 10; // px stranice oko bloka za isečak (i zakrpu na njegovom mestu)

/** Okvir isečka oko bloka, unutar stranice. */
export function cropRect(block: { x: number; y: number; width: number; height: number }, page: { width: number; height: number }) {
  const x = Math.max(0, Math.round(block.x - CROP_MARGIN));
  const y = Math.max(0, Math.round(block.y - CROP_MARGIN));
  const right = Math.min(page.width, Math.round(block.x + block.width + CROP_MARGIN));
  const bottom = Math.min(page.height, Math.round(block.y + block.height + CROP_MARGIN));
  return { x, y, width: right - x, height: bottom - y };
}

/** Slika uklopljena u okvir bez izobličenja, na sredini (AI aplikacije vraćaju drugu veličinu i odnos strana). */
export function fitInto(box: { x: number; y: number; width: number; height: number }, image: { width: number; height: number }) {
  if (image.width <= 0 || image.height <= 0) return box;
  const scale = Math.min(box.width / image.width, box.height / image.height);
  const width = image.width * scale;
  const height = image.height * scale;
  return { x: box.x + (box.width - width) / 2, y: box.y + (box.height - height) / 2, width, height };
}
