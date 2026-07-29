"use client";

import { useEffect, useState } from "react";

import {
  POINTER_MODE_COARSE,
  POINTER_MODE_FINE,
  resolvePointerModeFromEvent,
} from "./pointerMode.mjs";

export { POINTER_MODE_COARSE, POINTER_MODE_FINE, resolvePointerModeFromEvent };

export default function usePointerMode() {
  // Default to fine on the server and on first paint. Desktop hover is the
  // existing behaviour and must never be lost to a hydration flash.
  const [mode, setMode] = useState(POINTER_MODE_FINE);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    // Seed from capability before any user input arrives. Without this the
    // first deliberate tap on a phone would be spent switching the mode, and
    // the user would have to tap twice to inspect a point.
    if (typeof window.matchMedia === "function") {
      const hoverQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
      setMode(hoverQuery.matches ? POINTER_MODE_FINE : POINTER_MODE_COARSE);
    }

    const handlePointerDown = (event) => {
      setMode((current) => resolvePointerModeFromEvent(event, current));
    };

    // Capture phase: on a hybrid device the mode flips while the gesture is
    // still travelling down the tree, so the chart's own bubble-phase handling
    // of that very same gesture already sees the correct mode.
    window.addEventListener("pointerdown", handlePointerDown, { capture: true, passive: true });
    return () => window.removeEventListener("pointerdown", handlePointerDown, { capture: true });
  }, []);

  return mode;
}
