"use client";

import { useEffect, useMemo, useState } from "react";

import InterpretationBadge from "@/components/ui/InterpretationBadge";
import { getInterpretationTone } from "@/lib/explore/interpretationTone";

function toOptionalImageUrl(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const text = String(value).trim();
  return text || null;
}

function getInitials(name) {
  const words = String(name || "")
    .split(/\s+/)
    .map((word) => word.trim())
    .filter(Boolean);

  if (words.length === 0) {
    return "PK";
  }

  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

export default function SetIdentity({
  target,
  interpretationLabel = null,
  tier = null,
  recommendationSeverity = null,
  interpretationBadgeClassName = "",
  /**
   * "default" keeps the original roomy identity block. "compact" is the
   * Explore dense-table variant: a small logo, one title line, and the era +
   * interpretation collapsed onto a single supporting line as plain text
   * rather than another pill inside the row.
   */
  variant = "default",
}) {
  const name = String(target?.name || target?.target_id || "Unknown Set");

  const logoUrl = toOptionalImageUrl(target?.logo_image_url);
  const symbolUrl = toOptionalImageUrl(target?.symbol_image_url);
  const imageCandidates = useMemo(() => {
    const urls = [];
    if (logoUrl) {
      urls.push(logoUrl);
    }
    if (symbolUrl && symbolUrl !== logoUrl) {
      urls.push(symbolUrl);
    }
    return urls;
  }, [logoUrl, symbolUrl]);

  const [candidateIndex, setCandidateIndex] = useState(0);
  const [showImage, setShowImage] = useState(imageCandidates.length > 0);

  useEffect(() => {
    setCandidateIndex(0);
    setShowImage(imageCandidates.length > 0);
  }, [imageCandidates]);

  const activeSrc = showImage ? imageCandidates[candidateIndex] || null : null;

  const handleImageError = () => {
    const nextIndex = candidateIndex + 1;
    if (nextIndex < imageCandidates.length) {
      setCandidateIndex(nextIndex);
      return;
    }
    setShowImage(false);
  };

  if (variant === "compact") {
    const tone = interpretationLabel
      ? getInterpretationTone({ label: interpretationLabel, rankTier: tier, severity: recommendationSeverity })
      : null;

    return (
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-8 w-8 flex-none items-center justify-center overflow-hidden rounded-md bg-[rgba(255,255,255,0.045)]">
          {activeSrc ? (
            <img
              src={activeSrc}
              alt=""
              className="h-[86%] w-[86%] object-contain"
              loading="lazy"
              decoding="async"
              onError={handleImageError}
            />
          ) : (
            <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
              {getInitials(name)}
            </span>
          )}
        </div>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold leading-tight text-[var(--text-primary)]">{name}</p>
          <p className="mt-0.5 truncate text-[11px] leading-tight text-[var(--text-secondary)]">
            {target?.era ? <span>{target.era}</span> : null}
            {target?.era && interpretationLabel ? <span aria-hidden="true"> · </span> : null}
            {interpretationLabel ? (
              <span className="font-medium" style={tone ? { color: tone.textColor } : undefined}>
                {interpretationLabel}
              </span>
            ) : null}
          </p>
        </div>
      </div>
    );
  }

  const textBlock = (
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-semibold text-[var(--text-primary)] sm:text-base">{name}</p>
      {target?.era ? <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">{target.era}</p> : null}
      {interpretationLabel ? (
        <div className="mt-2 min-w-0 max-w-full overflow-hidden">
          <InterpretationBadge
            label={interpretationLabel}
            rankTier={tier}
            severity={recommendationSeverity}
            className={interpretationBadgeClassName}
          />
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="flex min-w-0 items-start gap-4">
      <div className="flex h-[4.25rem] w-[4.25rem] flex-none items-center justify-center overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] sm:h-[4.9rem] sm:w-[4.9rem]">
        {activeSrc ? (
          <img
            src={activeSrc}
            alt={`${name} logo`}
            className="h-[82%] w-[82%] object-contain"
            loading="lazy"
            decoding="async"
            onError={handleImageError}
          />
        ) : (
          <span className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {getInitials(name)}
          </span>
        )}
      </div>
      {textBlock}
    </div>
  );
}
