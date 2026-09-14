"use client";

import { useState } from "react";
import Link from "next/link";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import InfoPopover from "@/components/ui/InfoPopover";
import RankBadge from "@/components/ui/RankBadge";
import RipScoreSurface from "@/components/explore/RipScoreSurface.jsx";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import { publicLeaderScoreTier } from "@/components/explore/ripTierPresentation.mjs";
import { selectChaseAccessibilityPresentation } from "@/components/explore/chaseAccessibilityPresentationSelector.mjs";
import {
  finite,
  formatStrength,
  pluralFamilyLabel,
  productCompositionSummary,
} from "./productDetailModel.mjs";

const money = (value) =>
  finite(value) === null
    ? "Unavailable"
    : finite(value).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
      });
const percent = (value) =>
  finite(value) === null
    ? "Unavailable"
    : `${(finite(value) * 100).toFixed(1).replace(/\.0$/, "")}%`;

export function ProductRipLock() {
  return (
    <section
      data-product-rip-lock
      aria-labelledby="product-rip-lock-title"
      className={`set-glass-surface relative min-h-48 overflow-hidden rounded-2xl border ${planPresentation(INDEX_PLAN_PLUS).panelClassName}`}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 grid grid-cols-3 gap-3 p-5 opacity-20 blur-sm"
      >
        <span className="rounded-xl bg-white/10" />
        <span className="rounded-xl bg-white/10" />
        <span className="rounded-xl bg-white/10" />
      </div>
      <div className="relative z-10 flex min-h-48 flex-col items-center justify-center bg-[rgba(2,6,23,.68)] px-5 py-7 text-center">
        <PlanBadge plan={INDEX_PLAN_PLUS} />
        <h2 id="product-rip-lock-title" className="mt-2 text-2xl font-semibold">
          Unlock Product RIP
        </h2>
        <p className="mt-2 max-w-xl text-sm text-[var(--text-secondary)]">
          See how this product ranks within its format and what its modeled
          opening outcomes look like.
        </p>
        <PlanUpgradeLink requiredPlan={INDEX_PLAN_PLUS} source="sealed-product" className="mt-4"/>
      </div>
    </section>
  );
}

function ScoreCard({
  label,
  value,
  tier: tierValue,
  info,
  primary = false,
  children,
}) {
  return (
    <RipScoreSurface
      metricKey={label.toLowerCase().replaceAll(" ", "-")}
      tier={tierValue}
      prominent={primary}
      className={`p-4 ${primary ? "min-h-36 justify-center sm:p-5" : "sm:p-5"}`}
    >
      <div
        data-product-rip-score={label.toLowerCase().replaceAll(" ", "-")}
        className="relative z-[1] min-w-0"
      >
        <div className="flex items-start justify-between gap-3">
          <dt className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[.08em] text-[var(--text-primary)]">
            <span>{label}</span>
            {info ? <InfoPopover text={info} /> : null}
          </dt>
          <RankBadge
            rank={tierValue}
            format="tier"
            size={primary ? "supporting" : "compact"}
            subtle
          />
        </div>
        <dd
          className={`mt-5 font-semibold leading-none tabular-nums text-[var(--text-primary)] ${primary ? "text-4xl sm:text-5xl" : "text-3xl"}`}
        >
          {finite(value) === null ? (
            "Unavailable"
          ) : (
            <>
              {formatPublicRipScore(value)}{" "}
              <span className="ml-1 text-xs font-medium text-[var(--text-secondary)]">
                /10
              </span>
            </>
          )}
        </dd>
        {children}
      </div>
    </RipScoreSurface>
  );
}

function formatChasePercent(value) {
  return value === null || value === undefined ? "Unavailable" : `${value.toFixed(2)}%`;
}

/**
 * Chase Accessibility — Product RIP's compact presentation of the SET-LEVEL
 * ingredient of Market-Based Opening Quality. Reads ONLY the shared
 * `chaseAccessibilityPresentationSelector.mjs` contract (Phase 3/6/8) -
 * performs no arithmetic and fabricates no rank/tier/cohortSize. Labeled
 * "Parent set" (Phase 9) since this exact number is identical for every
 * sealed product of the same set/run - never implied to differ between an
 * ETB and a Booster Box of the same set.
 */
function ChaseAccessibilityCard({ chase }) {
  return (
    <div
      data-product-rip-score="chase-accessibility"
      className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)] p-4 sm:p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <dt className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[.08em] text-[var(--text-primary)]">
          <span>Chase Accessibility</span>
          <InfoPopover text={chase.technicalTooltip} />
        </dt>
        <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[.06em] text-[var(--text-secondary)]">
          Parent set
        </span>
      </div>
      <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">{chase.publicQuestion}</p>
      <dd className="mt-3 text-right text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
        {chase.publicScore === null ? "Unavailable" : <>{formatPublicRipScore(chase.publicScore)} <span className="text-xs text-[var(--text-secondary)]">/10</span></>}
      </dd>
      {!chase.available ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          {chase.statusReason || "Chase Accessibility is not currently available for this set."}
        </p>
      ) : (
        <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
          {chase.rank && chase.cohortSize ? `Set rank #${chase.rank} of ${chase.cohortSize}.` : "Parent-set rank unavailable."}
        </p>
      )}
    </div>
  );
}

export function ProductRipSection({ detail }) {
  const { rip, product } = detail;
  if (!rip.available)
    return (
      <section
        data-product-rip-unavailable
        className="set-glass-surface rounded-2xl border p-5"
      >
        <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
          Product RIP
        </p>
        <h2 className="mt-1 text-2xl font-semibold">
          Opening intelligence is not currently available for this product.
        </h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          This product does not have a current published, format-comparable
          opening result. Market and catalog information remain available.
        </p>
      </section>
    );
  const financialTier = publicLeaderScoreTier(rip.financialRipLeaderScore);
  const collectorTier = rip.collectorAppealTier;
  // Chase Accessibility - reused SHARED presentation contract (Phase 3/6),
  // never recomputed here. Reads `rip.publicRipContractV11.chaseAccessibility`
  // when present (the exact-run-authenticated backend projection), falling
  // back to plain `rip.chaseAccessibility` for any other caller shape.
  const chase = selectChaseAccessibilityPresentation(rip);
  return (
    <section
      data-product-rip-section
      aria-labelledby="product-rip-title"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
    >
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
        Product RIP · Index Plus
      </p>
      <h2 id="product-rip-title" className="mt-1 text-2xl font-semibold">
        How favorable is opening this exact product?
      </h2>
      <p className="mt-1.5 max-w-3xl text-sm text-[var(--text-secondary)]">
        Product RIP measures this product and ranks it only against comparable
        products of the same format.
      </p>
      <dl className="mt-4 grid gap-3">
        <ScoreCard
          primary
          label="RIP Score"
          value={rip.overallRipLeaderScore}
          tier={rip.publicTier}
        >
          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--tier-border)] pt-4">
            <p className="text-sm font-semibold">{formatStrength(rip)}</p>
            <p className="text-xs text-[var(--text-secondary)]">
              <span className="font-semibold text-[var(--text-primary)]">
                Format Rank
              </span>{" "}
              · #{rip.familyRank} of {rip.familySize}{" "}
              {pluralFamilyLabel(product.productFamilyLabel)}
            </p>
          </div>
        </ScoreCard>
      </dl>
      <div data-product-rip-formula className="my-3">
        <p className="text-sm text-[var(--text-secondary)]">RIP Score considers financial outcomes, chase accessibility, and collector appeal.</p>
      </div>
      <section
        data-three-pillar-summary="product"
        aria-label="Product RIP supporting scores"
        className="mt-1"
      >
        <dl className="mt-3 grid auto-rows-fr gap-3 sm:grid-cols-3">
          <div
            data-product-rip-score="financial-rip"
            className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)] p-4 sm:p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <dt className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[.08em] text-[var(--text-primary)]">
                <span>Financial RIP</span>
              </dt>
              <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[.06em] text-[var(--text-secondary)]">
                This product
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">
              Reflects this exact product&apos;s price, composition, and
              modeled opening outcomes.
            </p>
            <div className="mt-3">
              <RankBadge rank={financialTier} format="tier" size="compact" subtle />
            </div>
            <dd className="mt-3 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
              {finite(rip.financialRipLeaderScore) === null
                ? "Unavailable"
                : (
                  <>
                    {formatPublicRipScore(rip.financialRipLeaderScore)}{" "}
                    <span className="ml-1 text-xs font-medium text-[var(--text-secondary)]">/10</span>
                  </>
                )}
            </dd>
          </div>
          <ChaseAccessibilityCard chase={chase} />
          <ScoreCard label="Collector Appeal" value={rip.collectorAppealScore} tier={collectorTier} info="Collector Appeal reflects the collector-facing appeal of the product's parent set."><p className="mt-3 text-[11px] text-[var(--text-secondary)]"><span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 font-semibold uppercase tracking-[.06em]">Parent set</span></p></ScoreCard>
        </dl>
      </section>
    </section>
  );
}

export const SUPPORTING_OUTCOMES = [
  [
    "Chance to Recover Cost",
    "chanceToRecoverCost",
    "Modeled probability that the opening's gross market value reaches or exceeds the product's current market price.",
    percent,
  ],
  [
    "Entertainment Cost",
    "entertainmentCost",
    "Purchase price minus modeled gross market value.",
    money,
  ],
];

function OutcomeRangeRail({ rip, currentPrice }) {
  const markers = [
    [
      "p05",
      "P05",
      "Low-End Opening",
      rip.p05Value,
      "95% of modeled openings finished at or above this value.",
    ],
    [
      "typical",
      "Typical",
      "Typical Opening",
      rip.medianValue,
      "The median modeled opening result — half of modeled openings finished above this value and half below it.",
    ],
    [
      "ev",
      "EV",
      "Expected Value",
      rip.expectedValue,
      "Average modeled gross market value across simulated openings.",
    ],
    [
      "price",
      "Price",
      "Current Product Price",
      currentPrice,
      "The current tracked product price used for cost comparisons.",
    ],
    [
      "p95",
      "P95",
      "Realistic Upside",
      rip.p95Value,
      "Approximately 5% of modeled openings reached this value or higher.",
    ],
    [
      "p99",
      "P99",
      "Jackpot Upside",
      rip.p99Value,
      "Approximately 1% of modeled openings reached this value or higher.",
    ],
  ].map(([key, label, title, raw, description]) => ({
    key,
    label,
    title,
    value: finite(raw),
    description,
    price: key === "price",
  }));
  const available = markers.filter(({ value }) => value !== null);
  const [activeKey, setActiveKey] = useState("ev");
  if (!available.length) return null;
  const max = Math.max(...available.map(({ value }) => value), 1);
  const active = available.find(({ key }) => key === activeKey) || available[0];
  const activate = (key) => setActiveKey(key);
  return (
    <div
      data-opening-value-milestones
      className="mt-4 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(145deg,rgba(15,23,42,.7),rgba(2,8,23,.42))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,.045)] sm:p-5"
    >
      <div>
        <h3 className="text-base font-semibold">Opening Value Milestones</h3>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          Compare low-end, typical, average, and upside outcomes against the
          current product price.
        </p>
      </div>
      <div
        role="list"
        aria-label="Opening value milestone choices"
        className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6"
      >
        {markers.map((marker) => {
          const selected = marker.key === active.key;
          return (
            <button
              key={marker.key}
              type="button"
              disabled={marker.value === null}
              aria-pressed={selected}
              onClick={() => activate(marker.key)}
              onFocus={() => marker.value !== null && activate(marker.key)}
              onMouseEnter={() => marker.value !== null && activate(marker.key)}
              className={`min-h-12 rounded-lg border px-2 py-2 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-40 ${selected ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)]" : "border-[var(--border-subtle)] bg-white/[.025] hover:bg-white/[.05]"}`}
            >
              <span
                className={`block text-[10px] font-bold uppercase tracking-[.08em] ${marker.price ? "text-amber-200" : "text-[var(--text-secondary)]"}`}
              >
                {marker.label}
              </span>
              <span className="mt-1 block text-xs font-semibold tabular-nums">
                {money(marker.value)}
              </span>
            </button>
          );
        })}
      </div>
      <div className="relative mx-2 mt-8 h-8">
        <div className="absolute inset-x-0 top-3 h-2 rounded-full border border-white/10 bg-[linear-gradient(90deg,rgba(248,113,113,.2),rgba(56,189,248,.25),rgba(167,139,250,.3))]" />
        {available.map((marker) => {
          const selected = marker.key === active.key;
          return (
            <button
              key={marker.key}
              type="button"
              data-outcome-marker={marker.key}
              aria-label={`${marker.title}: ${money(marker.value)}. ${marker.description}`}
              aria-pressed={selected}
              onClick={() => activate(marker.key)}
              onFocus={() => activate(marker.key)}
              onMouseEnter={() => activate(marker.key)}
              className={`absolute top-0 z-[1] -translate-x-1/2 rounded-full border-2 border-slate-950 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${marker.price ? "bg-amber-300" : "bg-[var(--accent)]"} ${selected ? "h-8 w-8 scale-110 shadow-[0_0_0_5px_rgba(255,255,255,.1)]" : "mt-1 h-6 w-6 opacity-80 hover:opacity-100"}`}
              style={{
                left: `${Math.max(1, Math.min(99, (marker.value / max) * 100))}%`,
              }}
            />
          );
        })}
      </div>
      <div
        data-active-milestone
        aria-live="polite"
        className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-black/15 p-4"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p
            className={`text-xs font-bold uppercase tracking-[.09em] ${active.price ? "text-amber-200" : "text-[var(--accent)]"}`}
          >
            {active.title}
          </p>
          <p className="text-2xl font-semibold tabular-nums">
            {money(active.value)}
          </p>
        </div>
        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
          {active.description}
        </p>
      </div>
    </div>
  );
}

export function ProductOpeningProfile({ rip, currentPrice }) {
  const value = (key) =>
    key === "entertainmentCost"
      ? rip.entertainmentCost?.entertainmentCost
      : rip[key];
  const composition = rip.composition || {};
  const compositionView = productCompositionSummary(composition);
  return (
    <section
      data-opening-outcome-profile
      aria-labelledby="opening-profile-title"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
    >
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
        Index Plus
      </p>
      <h2 id="opening-profile-title" className="mt-1 text-2xl font-semibold">
        Opening Outcome Profile
      </h2>
      <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
        What does opening this product actually look like?
      </p>
      <OutcomeRangeRail rip={rip} currentPrice={currentPrice} />
      <dl
        data-supporting-outcome-metrics
        className="mt-4 grid gap-2 sm:grid-cols-2"
      >
        {SUPPORTING_OUTCOMES.map(([label, key, info, formatter]) => (
          <div
            data-supporting-outcome={key}
            key={key}
            className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)] p-4"
          >
            <dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.07em] text-[var(--text-secondary)]">
              {label}
              <InfoPopover text={info} />
            </dt>
            <dd className="mt-2 text-xl font-semibold tabular-nums">
              {formatter(value(key))}
            </dd>
          </div>
        ))}
      </dl>
      {compositionView.available ? (
        <div
          data-product-composition
          className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-white/[.025] p-4"
        >
          <p className="text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
            Product Composition
          </p>
          <p className="mt-2 text-lg font-semibold">
            {compositionView.summary || "Modeled guaranteed value included"}
          </p>
          {compositionView.guaranteedValue !== null ? (
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Guaranteed component value{" "}
              <strong className="ml-1 text-[var(--text-primary)]">
                {money(compositionView.guaranteedValue)}
              </strong>
            </p>
          ) : null}
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            Accessories are not assigned modeled market value under the current
            opening model.
          </p>
        </div>
      ) : null}
      <details className="mt-3 rounded-xl border border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
        <summary className="cursor-pointer font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
          Additional outcome details
        </summary>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt>Expected Loss When Losing</dt>
            <dd className="font-semibold text-[var(--text-primary)]">
              {money(rip.expectedLossWhenLosing)}
            </dd>
          </div>
          <div>
            <dt>Median Loss When Losing</dt>
            <dd className="font-semibold text-[var(--text-primary)]">
              {money(rip.medianLossWhenLosing)}
            </dd>
          </div>
          <div>
            <dt>Modeled Return Ratio</dt>
            <dd className="font-semibold text-[var(--text-primary)]">
              {finite(rip.totalValueToCostRatio) === null
                ? "Unavailable"
                : `${(rip.totalValueToCostRatio * 100).toFixed(1)}%`}
            </dd>
          </div>
          <div>
            <dt>Entertainment Cost Per Pack</dt>
            <dd className="font-semibold text-[var(--text-primary)]">
              {money(rip.entertainmentCost?.entertainmentCostPerPackEquivalent)}
            </dd>
          </div>
        </dl>
        <p className="mt-4">
          Entertainment Cost uses gross modeled market value. Marketplace fees,
          shipping, liquidation friction, bid/ask spread, and grading are not
          deducted or assumed. It is the price of the modeled opening
          experience, not a loss prediction.
        </p>
      </details>
    </section>
  );
}
