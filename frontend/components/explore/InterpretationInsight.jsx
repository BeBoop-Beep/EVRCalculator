"use client";

import { useMemo, useState } from "react";

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

function getSeverityStyles(severity) {
  switch (severity) {
    case "positive":
      return {
        leftBorder: "border-l-[rgba(45,212,191,0.7)]",
        dot: "bg-[rgba(45,212,191,0.9)]",
        badge: "border-[rgba(45,212,191,0.35)] text-[rgba(153,246,228,0.95)]",
      };
    case "neutral":
      return {
        leftBorder: "border-l-[rgba(96,165,250,0.6)]",
        dot: "bg-[rgba(125,211,252,0.9)]",
        badge: "border-[rgba(125,211,252,0.35)] text-[rgba(186,230,253,0.95)]",
      };
    case "caution":
      return {
        leftBorder: "border-l-[rgba(251,191,36,0.8)]",
        dot: "bg-[rgba(251,191,36,0.95)]",
        badge: "border-[rgba(251,191,36,0.35)] text-[rgba(253,230,138,0.95)]",
      };
    case "negative":
      return {
        leftBorder: "border-l-[rgba(251,113,133,0.8)]",
        dot: "bg-[rgba(251,113,133,0.95)]",
        badge: "border-[rgba(251,113,133,0.35)] text-[rgba(254,205,211,0.95)]",
      };
    default:
      return {
        leftBorder: "border-l-[var(--border-subtle)]",
        dot: "bg-[rgba(148,163,184,0.85)]",
        badge: "border-[var(--border-subtle)] text-[var(--text-secondary)]",
      };
  }
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

  const severityStyles = getSeverityStyles(sectionMeta?.severity);
  const bodyTextClass = compact ? "text-sm leading-snug" : "text-sm leading-relaxed";
  const wrapperClass = compact
    ? ["border-l-2", severityStyles.leftBorder, "pl-3 py-1.5 bg-transparent"].join(" ")
    : ["border-l-2", severityStyles.leftBorder, "pl-4 py-2.5 bg-[rgba(255,255,255,0.025)] rounded-r-lg"].join(" ");

  const visibleEvidence = !showAllWhenExpanded || !isOpen ? evidence.slice(0, maxEvidence) : evidence;
  const hasHiddenEvidence = evidence.length > visibleEvidence.length;

  return (
    <div
      className={[
        wrapperClass,
        className,
      ].join(" ")}
    >
      {label ? (
        <div className="mb-1.5 flex items-center gap-2">
          <span className={["h-1.5 w-1.5 rounded-full", severityStyles.dot].join(" ")} aria-hidden="true" />
          <span
            className={[
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
              severityStyles.badge,
            ].join(" ")}
          >
            {label}
          </span>
        </div>
      ) : null}

      {summary ? <p className={[bodyTextClass, "text-[var(--text-primary)]"].join(" ")}>{summary}</p> : null}

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
