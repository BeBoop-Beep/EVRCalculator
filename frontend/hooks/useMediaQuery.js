"use client";

import { useEffect, useState } from "react";

// Reads a media query reactively. `initialValue` is what SSR and the first
// client paint assume — always pass the desktop answer, so a hydration flash
// can never momentarily strip desktop behaviour.
export default function useMediaQuery(query, initialValue = false) {
  const [matches, setMatches] = useState(initialValue);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const mediaQueryList = window.matchMedia(query);
    const update = () => setMatches(mediaQueryList.matches);
    update();
    if (typeof mediaQueryList.addEventListener === "function") {
      mediaQueryList.addEventListener("change", update);
      return () => mediaQueryList.removeEventListener("change", update);
    }
    return undefined;
  }, [query]);

  return matches;
}
