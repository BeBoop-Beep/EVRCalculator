"use client";

import { useEffect, useRef, useState } from "react";

// Recharts' ResponsiveContainer warns ("The width(0) and height(0) of chart
// should be greater than 0…") and renders nothing when it mounts inside a
// container that measures 0x0 — which happens when a chart mounts in the same
// commit that builds its layout (hydration, tab switches) or when a
// percentage-height chain resolves against a parent whose height is not yet
// definite (e.g. min-h-*/flex-1 wrappers, where height:100% computes to 0).
// ChartFrame reserves the chart's box via className (which must carry an
// explicit height, e.g. h-[20rem]) and only mounts its children once that box
// has actually measured non-zero, inside an absolutely-positioned fill so
// percentage-based ResponsiveContainer sizing always resolves against a
// definite rectangle.
export default function ChartFrame({ className = "", children }) {
  const frameRef = useRef(null);
  const [isMeasured, setIsMeasured] = useState(false);

  useEffect(() => {
    const element = frameRef.current;
    if (!element) {
      return undefined;
    }
    if (typeof ResizeObserver === "undefined") {
      // No way to observe layout — fall back to mounting immediately rather
      // than hiding the chart forever.
      setIsMeasured(true);
      return undefined;
    }

    let observer = null;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setIsMeasured(true);
        if (observer) {
          observer.disconnect();
          observer = null;
        }
        return true;
      }
      return false;
    };

    if (measure()) {
      return undefined;
    }
    observer = new ResizeObserver(() => {
      measure();
    });
    observer.observe(element);
    return () => {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
    };
  }, []);

  return (
    <div ref={frameRef} className={["relative", className].filter(Boolean).join(" ")}>
      {isMeasured ? <div className="absolute inset-0">{children}</div> : null}
    </div>
  );
}
