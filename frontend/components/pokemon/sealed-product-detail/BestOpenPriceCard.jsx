"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { bestOpenThresholdCopy, bestOpenStrategyCopy, bestOpenUnavailableCopy } from "./bestOpenPriceDetailModel.mjs";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

function numeric(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateLabel(value) {
  if (!value) return "Unavailable";
  const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

const HELP = "Best-Open Price is the highest acquisition price at which this product would rank #1 against the published Full Market cohort, using whole units within its fixed comparison budget. Non-leaders search at or below their published price; the leader searches upward. The threshold holds every other product at that publication's price; a newer live product price is shown separately and never silently rescored against an older cohort.";

export default function BestOpenPriceCard({ bestOpen, market }) {
  if (!bestOpen) return null;
  if (bestOpen.available !== true) {
    return (
      <section
        data-product-best-open-price
        data-best-open-available="false"
        className="set-glass-surface rounded-2xl border p-4 sm:p-5"
      >
        <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
          Best-Open Price · Full Market
        </p>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          {bestOpenUnavailableCopy(bestOpen.reason)}
        </p>
      </section>
    );
  }

  const threshold = numeric(bestOpen.bestOpenPrice);
  if (threshold === null) return null;
  const sourcePrice = numeric(bestOpen.sourceUnitPrice);
  const livePrice = numeric(market?.currentPrice);
  const liveDelta = livePrice === null ? null : livePrice - threshold;
  const sourceRank = numeric(bestOpen.sourceBudgetRank);
  const cohortSize = numeric(bestOpen.sourceCohortSize);

  const thresholdContext = bestOpenThresholdCopy(bestOpen);
  const strategyContext = bestOpenStrategyCopy(bestOpen);

  const liveComparison = liveDelta === null
    ? null
    : Math.abs(liveDelta) < 0.005
      ? "The current tracked price is at the published Best-Open threshold."
      : `The current tracked price is ${money.format(Math.abs(liveDelta))} ${liveDelta > 0 ? "above" : "below"} the published threshold.`;

  return (
    <section
      data-product-best-open-price
      data-best-open-available="true"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
      aria-labelledby="product-best-open-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
            <span>Best-Open Price · Full Market</span>
            <InfoPopover text={HELP} />
          </p>
          <h2 id="product-best-open-title" className="mt-2 text-3xl font-semibold tabular-nums sm:text-4xl">
            {money.format(threshold)}
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-[var(--text-secondary)]">
            {thresholdContext}
          </p>
          {strategyContext ? <p data-best-open-strategy className="mt-1 text-xs text-[var(--text-secondary)]">{strategyContext}</p> : null}
        </div>
        <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
          Prices as of {dateLabel(bestOpen.sourceMarketDate)}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.32)] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">Ranking source price</p>
          <p className="mt-1 text-lg font-semibold tabular-nums">{sourcePrice === null ? "Unavailable" : money.format(sourcePrice)}</p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{dateLabel(bestOpen.sourceMarketDate)}</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.32)] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">Current tracked price</p>
          <p className="mt-1 text-lg font-semibold tabular-nums">{livePrice === null ? "Unavailable" : money.format(livePrice)}</p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{dateLabel(market?.marketDate)}</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.32)] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">Published Full Market rank</p>
          <p className="mt-1 text-lg font-semibold tabular-nums">
            {sourceRank === null ? "Unavailable" : `#${sourceRank}${cohortSize === null ? "" : ` of ${cohortSize}`}`}
          </p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">Bound to the same threshold source</p>
        </div>
      </div>

      {liveComparison ? (
        <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
          {liveComparison} This is a price comparison only: the Best-Open threshold remains bound to the Full Market cohort dated {dateLabel(bestOpen.sourceMarketDate)} until the next prepared publication completes.
        </p>
      ) : null}
    </section>
  );
}
