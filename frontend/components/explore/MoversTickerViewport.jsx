"use client";

import React, { useEffect, useRef, useState } from "react";

export default function MoversTickerViewport({ hasItems, items, renderSequence, fallback }) {
  const viewportRef = useRef(null);
  const sequenceRef = useRef(null);
  const [sequenceWidth, setSequenceWidth] = useState(0);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const [isFocusWithin, setIsFocusWithin] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setPrefersReducedMotion(query.matches);
    update();
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", update);
      return () => query.removeEventListener("change", update);
    }
    return undefined;
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    const sequence = sequenceRef.current;
    if (!viewport || !sequence) {
      setIsOverflowing(false);
      return undefined;
    }
    const measure = () => {
      const width = sequence.scrollWidth || 0;
      setSequenceWidth(width);
      setIsOverflowing(width > viewport.clientWidth + 1);
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    observer.observe(sequence);
    return () => observer.disconnect();
  }, [hasItems, items]);

  const shouldRenderMarquee = hasItems && isOverflowing && !prefersReducedMotion;
  const isMarqueePaused = isFocusWithin;
  const marqueeDurationSeconds = Math.max(20, Math.round(sequenceWidth / 40));

  const handleBlurCapture = (event) => {
    const nextTarget = event?.relatedTarget || null;
    if (viewportRef.current && nextTarget && viewportRef.current.contains(nextTarget)) {
      return;
    }
    setIsFocusWithin(false);
  };

  return (
    <div
      ref={viewportRef}
      role="region"
      aria-label="7-day market movers"
      onFocusCapture={() => setIsFocusWithin(true)}
      onBlurCapture={handleBlurCapture}
      className={`index-ticker-viewport flex h-full min-w-0 flex-1 items-center overflow-y-hidden ${
        shouldRenderMarquee ? "overflow-x-hidden" : "overflow-x-auto"
      }`}
    >
      {hasItems ? (
        <div
          className={`flex w-max items-center ${shouldRenderMarquee ? "index-ticker-track" : ""}`.trim()}
          style={
            shouldRenderMarquee
              ? {
                  "--index-ticker-duration": `${marqueeDurationSeconds}s`,
                  ...(isMarqueePaused ? { animationPlayState: "paused" } : {}),
                }
              : undefined
          }
        >
          {renderSequence(false, sequenceRef)}
          {shouldRenderMarquee ? renderSequence(true) : null}
        </div>
      ) : (
        fallback
      )}
    </div>
  );
}
