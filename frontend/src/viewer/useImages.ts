import { useEffect, useState } from "react";

const loaded = new Map<string, HTMLImageElement>();

/** Slike za Konva canvas (slova naslova), učitane jednom po adresi i zapamćene. */
export function useImages(urls: string[]): Map<string, HTMLImageElement> {
  const [, setCount] = useState(0);
  const key = [...new Set(urls)].join("\n");

  useEffect(() => {
    let active = true;
    for (const url of key ? key.split("\n") : []) {
      if (loaded.has(url)) continue;
      const image = new Image();
      image.onload = () => {
        loaded.set(url, image);
        if (active) setCount((count) => count + 1);
      };
      image.src = url;
    }
    return () => {
      active = false;
    };
  }, [key]);

  return loaded;
}
