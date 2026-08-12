"use client";

// React is imported explicitly (rather than relying on the bundler's automatic
// JSX runtime) so this component can be rendered directly under `tsx --test`,
// which compiles JSX to React.createElement. SetIdentity.test.jsx does exactly
// that to assert on the rendered tree instead of on the source text.
import React, { useEffect, useMemo, useState } from "react";

// Relative, not the "@/" alias: SetIdentity.test.jsx renders this component
// directly under `tsx --test`, which does not resolve the bundler alias.
import { SET_LOGO_WIDTH, optimizedImageUrl } from "../../lib/images/remoteImageDelivery.mjs";

// IDENTITY ONLY. This block used to render an interpretation verdict badge next
// to the set name, fed by the retired Profit/Safety/Stability engine's
// `leaderboard_label` / `canonical_recommendation_header` and toned by
// `recommendation_severity`. Those describe a superseded model, so the badge and
// its tone are gone; tier and rank are shown by the caller's own cells.

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
  /**
   * "default" keeps the original roomy identity block. "compact" is the
   * Explore dense-table variant: a small logo, one title line, and the era on a
   * single supporting line rather than another pill inside the row.
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

  // SET_LOGO_WIDTH, matching the set hero and page atmosphere: this is the same
  // logo those slots paint, so a shared width means a shared cache entry rather
  // than a second transform of identical artwork.
  const activeSrc = optimizedImageUrl(showImage ? imageCandidates[candidateIndex] || null : null, SET_LOGO_WIDTH);

  const handleImageError = () => {
    const nextIndex = candidateIndex + 1;
    if (nextIndex < imageCandidates.length) {
      setCandidateIndex(nextIndex);
      return;
    }
    setShowImage(false);
  };

  if (variant === "compact") {
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
          {target?.era ? (
            <p className="mt-0.5 truncate text-[11px] leading-tight text-[var(--text-secondary)]">{target.era}</p>
          ) : null}
        </div>
      </div>
    );
  }

  const textBlock = (
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-semibold text-[var(--text-primary)] sm:text-base">{name}</p>
      {target?.era ? <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">{target.era}</p> : null}
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
