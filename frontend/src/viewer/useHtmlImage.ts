import { useEffect, useState } from "react";

interface State {
  url: string;
  key: string | number;
  image: HTMLImageElement | null;
  failed: boolean;
}

/**
 * Učitava sliku za Konva canvas. Dok se učitava nova verzija iste stranice (isti `key`, npr. posle
 * poteza četkice), vraća prethodnu sliku, da prikaz ne trepće; za drugu stranicu vraća null.
 */
export function useHtmlImage(url: string, key: string | number = url) {
  const [state, setState] = useState<State | null>(null);

  useEffect(() => {
    const image = new Image();
    let active = true;
    image.onload = () => active && setState({ url, key, image, failed: false });
    image.onerror = () => active && setState({ url, key, image: null, failed: true });
    image.src = url;
    return () => {
      active = false;
    };
  }, [url, key]);

  if (state?.url === url) return state;
  if (state?.key === key && state.image) return { url, key, image: state.image, failed: false };
  return { url, key, image: null, failed: false };
}
