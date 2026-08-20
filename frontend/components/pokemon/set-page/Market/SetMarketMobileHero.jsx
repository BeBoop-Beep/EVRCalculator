"use client";

import React from "react";

import { buildHeroMetrics } from "./setMarketMobileModel.mjs";

// ---------------------------------------------------------------------------
// Mobile Market hero — the set's identity as a compact dashboard header.
//
// This is NOT the set picker. The picker lives in the pinned tab block above
// and stays the only way to change sets; duplicating a second trigger here
// would put two operable listboxes for one setting on the same screen. What
// this adds is the CONTEXT the pinned strip cannot afford to carry at every
// scroll position: era, release date, checklist size and RIP standing.
//
// Layout: art on the left, identity stacked beside it, and a metric row banded
// underneath. Metrics are individually optional — `buildHeroMetrics` drops any
// reading the set does not publish — so a set with no RIP rank yields a two-cell
// row rather than a cell containing an em dash.
// ---------------------------------------------------------------------------

function TierPill({ tier, style }) {
  if (!tier) return null;
  return (
    <span
      data-market-mobile-hero-tier
      className="inline-flex flex-none items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase leading-tight tracking-[0.06em]"
      style={style}
    >
      {`${tier} Tier`}
    </span>
  );
}

export default function SetMarketMobileHero({
  id,
  setName,
  era = null,
  logoUrl = null,
  releaseDateText = null,
  totalCards = null,
  ripTier = null,
  ripTierStyle = undefined,
  ripRank = null,
  ripCohortSize = null,
}) {
  const metrics = buildHeroMetrics({ releaseDateText, totalCards, ripRank, ripCohortSize });

  return (
    <section
      id={id}
      data-market-mobile-hero
      className="set-context-premium relative min-w-0 overflow-hidden rounded-2xl border"
      aria-label={`${setName} set overview`}
    >
      {/* The set's own artwork, bloomed behind the identity block. It is the
          same logo the page already fetched, so this costs no extra request —
          scaled up, blurred and masked to a soft right-edge falloff so it reads
          as atmosphere rather than as a second, competing logo. */}
      {logoUrl ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-6 -top-6 h-[9rem] w-[9rem] bg-contain bg-right-top bg-no-repeat opacity-[0.10] blur-[2px]"
          style={{
            backgroundImage: `url("${logoUrl}")`,
            maskImage: "radial-gradient(closest-side, #000 30%, transparent 100%)",
            WebkitMaskImage: "radial-gradient(closest-side, #000 30%, transparent 100%)",
          }}
        />
      ) : null}

      <div className="relative flex min-w-0 items-center gap-3 px-3.5 pb-3 pt-3.5">
        {logoUrl ? (
          <span className="flex h-14 w-[4.5rem] flex-none items-center justify-center tab:h-16 tab:w-20">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={logoUrl}
              alt=""
              aria-hidden="true"
              className="max-h-14 w-auto max-w-[4.5rem] object-contain tab:max-h-16 tab:max-w-20"
              decoding="async"
            />
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <h1
            data-market-mobile-hero-name
            className="set-context-identity min-w-0 break-words text-[19px] font-semibold leading-[1.15] text-[var(--text-primary)]"
          >
            {setName}
          </h1>
          <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {era ? (
              <p className="min-w-0 truncate text-[11px] font-medium leading-tight text-[var(--text-secondary)]">{era}</p>
            ) : null}
            <TierPill tier={ripTier} style={ripTierStyle} />
          </div>
        </div>
      </div>

      {/* Flex, not a grid with a computed template: `important: true` in
          tailwind.config.js makes every utility !important, so an inline
          `gridTemplateColumns` loses to `grid-cols-*` and a one-metric row kept
          painting three columns' worth of empty band. Equal flex children
          simply divide however many cells survived. */}
      {metrics.length > 0 ? (
        <div
          data-market-mobile-hero-metrics
          className="relative flex gap-px border-t border-[var(--border-subtle)] bg-[var(--border-subtle)]"
        >
          {metrics.map((metric) => (
            <div key={metric.key} className="min-w-0 flex-1 bg-[rgba(8,17,31,0.30)] px-3 py-2.5">
              <p className="truncate text-[9.5px] font-bold uppercase leading-none tracking-[0.11em] text-[rgba(199,214,234,0.6)]">
                {metric.label}
              </p>
              <p className="mt-1.5 min-w-0 truncate text-[13px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
                {metric.value}
                {metric.suffix ? (
                  <span className="ml-1 text-[10px] font-medium text-[var(--text-secondary)]">{metric.suffix}</span>
                ) : null}
              </p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
