"use client";

import { useEffect, useRef } from "react";
import { markSectionTiming, debugSectionTiming } from "@/lib/perf/sectionTiming";

// Records how long a section spent in "loading" before reaching "success" or
// "error", and reports it under the section's own metric name (e.g.
// "setValueMs", "marketMoversMs", "criticalHeroMs"). Pair with
// useSectionFetchState's status. One call per section component.
export function useSectionTiming(
  sectionName,
  status,
  { setId = null, tab = null, logPrefix = "[section-timing]" } = {}
) {
  const startedAtRef = useRef(null);
  const reportedForRef = useRef(null);

  useEffect(() => {
    if (status === "loading") {
      startedAtRef.current = typeof performance !== "undefined" ? performance.now() : Date.now();
      reportedForRef.current = null;
      return;
    }

    if (status !== "success" && status !== "error") {
      return;
    }

    const reportKey = `${setId || ""}:${status}`;
    if (reportedForRef.current === reportKey || startedAtRef.current === null) {
      return;
    }
    reportedForRef.current = reportKey;

    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const elapsedMs = Math.round(now - startedAtRef.current);
    const metricName = `${sectionName}Ms`;

    markSectionTiming(`${sectionName}_${status}`, { setId, tab, elapsedMs });
    debugSectionTiming(logPrefix, metricName, { setId, tab, elapsedMs, status });
  }, [status, sectionName, setId, tab, logPrefix]);
}
