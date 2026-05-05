"use client";

import { useEffect, useMemo, useState } from "react";

import InterpretationBadge from "@/components/ui/InterpretationBadge";

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

  const textBlock = (
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-semibold text-[var(--text-primary)] sm:text-base">{name}</p>
      {target?.era ? <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">{target.era}</p> : null}
      {interpretationLabel ? (
        <div className="mt-2">
          <InterpretationBadge label={interpretationLabel} rankTier={tier} severity={recommendationSeverity} />
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