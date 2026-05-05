"use client";

import { useMemo, useState } from "react";

import InterpretationBadge from "@/components/ui/InterpretationBadge";
import { getCalloutAccentStyle, getInterpretationTone } from "@/lib/explore/interpretationTone";

function isMeaningfulEvidenceValue(value) {
  if (value === null || value === undefined) {
    return false;
  }
  const text = String(value).trim();
  if (!text) {
    return false;
  }
  return text !== "N/A" && text !== "—";
}

export default function InterpretationInsight({
  sectionMeta,
  fallbackSummary,
  compact = false,
  showEvidence = false,
  className = "",
  maxEvidence = 5,
  showAllWhenExpanded = false,
  evidenceLabel = "Why this matters",
  rankTier = null,
}) {
  const [isOpen, setIsOpen] = useState(false);

  const label = sectionMeta?.label || null;
  const summary = sectionMeta?.summary || fallbackSummary || null;

  const evidence = useMemo(() => {
    const list = Array.isArray(sectionMeta?.evidence) ? sectionMeta.evidence : [];
    return list
      .filter((item) => item && item.label)
      .filter((item) => isMeaningfulEvidenceValue(item.value));
  }, [sectionMeta?.evidence]);

  if (!label && !summary) {
    return null;
  }

  const tone = getInterpretationTone({
    label,
    rankTier,
    severity: sectionMeta?.severity,
  });
  const bodyTextClass = compact ? "text-sm leading-snug" : "text-sm leading-relaxed";
  const wrapperClass = compact
    ? ["border-l-2", "pl-3 py-1.5 bg-transparent"].join(" ")
    : ["border-l-2 rounded-r-lg pl-4 py-2.5"].join(" ");

  const visibleEvidence = !showAllWhenExpanded || !isOpen ? evidence.slice(0, maxEvidence) : evidence;
  const hasHiddenEvidence = evidence.length > visibleEvidence.length;

  return (
    <div
      className={[
        wrapperClass,
        className,
      ].join(" ")}
      style={
        compact
          ? {
              borderLeftColor: tone.accentColor,
              backgroundColor: "transparent",
              boxShadow: "none",
            }
          : getCalloutAccentStyle({ label, rankTier, severity: sectionMeta?.severity })
      }
    >
      {label ? (
        <div className="mb-1.5 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full" aria-hidden="true" style={{ backgroundColor: tone.dotColor }} />
          <InterpretationBadge label={label} rankTier={rankTier} severity={sectionMeta?.severity} className="px-2 py-0.5 text-[10px] tracking-[0.08em]" />
        </div>
      ) : null}

      {summary ? (
        <p className={[bodyTextClass, "text-[var(--text-primary)]"].join(" ")}>
          {summary}
        </p>
      ) : null}

      {showEvidence && evidence.length > 0 ? (
        <div className="mt-2.5">
          <button
            type="button"
            onClick={() => setIsOpen((current) => !current)}
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
          >
            <span>{isOpen ? "Hide evidence" : evidenceLabel}</span>
            <span aria-hidden="true" className={isOpen ? "rotate-180 transition-transform" : "transition-transform"}>▾</span>
          </button>

          {isOpen ? (
            <div className="mt-2 space-y-1.5">
              {visibleEvidence.map((item, index) => (
                <div
                  key={`${item.label}:${index}`}
                  className="flex items-start justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1.5"
                >
                  <span className="text-xs text-[var(--text-secondary)]">{item.label}</span>
                  <span className="text-xs font-medium text-[var(--text-primary)] text-right">{String(item.value)}</span>
                </div>
              ))}
              {hasHiddenEvidence ? <p className="text-[11px] text-[var(--text-secondary)]">Additional evidence available in backend metadata.</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
