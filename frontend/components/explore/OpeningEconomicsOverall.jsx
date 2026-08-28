"use client";

import React, { useState } from "react";
import Image from "next/image";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import InfoPopover from "@/components/ui/InfoPopover";
import styles from "./explore.module.css";
import local from "./openingEconomics.module.css";
import {
  UNAVAILABLE_LABEL,
  centsPerDollar,
  isAvailable,
  money,
  outcomeRangePositions,
  ratioAsPercent,
  valueDescent,
} from "./openingEconomicsSelector.mjs";

/**
 * The Overall lens.
 *
 * Answers one question — what does opening Pokemon look like economically —
 * and is deliberately NOT another leaderboard. Every number is read straight
 * from the published snapshot; nothing here is calculated in the browser.
 */

const METHODOLOGY = [
  "Every eligible modeled sealed product is normalized to an all-in per-pack equivalent.",
  "Within each set, represented product families receive equal weight and SKUs inside each family receive equal weight.",
  "Every modeled set receives equal weight globally.",
  "Typical Opening is the median of the weighted empirical product-opening distribution, not an average of product or set medians.",
  "Guaranteed modeled card components are included exactly once before normalization; accessories have zero modeled value.",
  "Card values are gross modeled market values before selling fees, shipping, grading, liquidity discounts, and taxes.",
];

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function OpeningDistribution({ scope, targets }) {
  const [lens, setLens] = useState("return");
  const distribution = lens === "return" ? scope.normalizedReturnPercentiles : scope.valuePerPackPercentiles;
  const points = Array.from({length:99},(_,index)=>{const percentile=index+1;const key=`p${String(percentile).padStart(2,"0")}`;return {key,percentile,value:Number(distribution?.[key])};}).filter(point=>Number.isFinite(point.value)&&point.value>0);
  const formatter = lens === "return" ? ratioAsPercent : money;
  const packs = (targets || []).map(target => ({target,fallback:target.logo_image_url||target.symbol_image_url}));
  const metrics = [
    ["Modeled Return", ratioAsPercent(scope.modeledReturnOnSpend)],
    ["Typical Retention", ratioAsPercent(scope.typicalRetention)],
    ["Chance to Recover Cost", ratioAsPercent(scope.chanceToRecoverCost)],
    ["Entertainment Cost / Pack", money(scope.averageEntertainmentCostPerPack)],
  ];
  return <section className={`${styles.surface} rounded-xl p-4 sm:p-5`} data-opening-distribution>
    <div className="grid grid-cols-2 gap-4 border-b border-[var(--ex-line)] pb-4 lg:grid-cols-4">{metrics.map(([label,value]) => <div key={label}><p className="text-[.65rem] uppercase tracking-wide text-[var(--text-secondary)]">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value || <Dash/>}</p></div>)}</div>
    <div className="mt-5 flex items-end justify-between gap-3"><div><h3 className="text-base font-semibold">Opening Distribution</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">Weighted empirical percentile / outcome curve across the modeled product cohort.</p></div><div className="flex rounded-lg border border-[var(--ex-line)] p-1"><button onClick={()=>setLens("return")} aria-pressed={lens==="return"} className="px-3 py-1 text-xs">Return %</button><button onClick={()=>setLens("value")} aria-pressed={lens==="value"} className="px-3 py-1 text-xs">Value / Pack</button></div></div>
    {points.length===99 ? <div className="mt-6" role="img" aria-label={`${lens === "return" ? "Normalized return" : "Value per pack"} P01 through P99 percentile curve`} data-percentile-points="99"><div className="flex h-52 items-end gap-px border-b border-[var(--ex-line-strong)]">{points.map(point=><div key={point.key} title={`${point.key.toUpperCase()} ${formatter(point.value)}`} className="min-w-0 flex-1 bg-[rgb(var(--ex-teal))]" style={{height:`${Math.max(1,Math.log1p(point.value)/Math.log1p(Math.max(...points.map(p=>p.value)))*100)}%`}}/>)}</div><div className="mt-2 flex justify-between text-[.65rem] text-[var(--text-secondary)]"><span>P01 {formatter(points[0].value)}</span><span>P50 {formatter(points[49].value)}</span><span>P99 {formatter(points[98].value)}</span></div><p className="mt-4 text-xs text-[var(--text-secondary)]">{lens === "return" ? `100% recovery threshold · P50 ${ratioAsPercent(scope.typicalRetention)} · Mean outcome retention ${ratioAsPercent(scope.meanOutcomeRetention)} · ${ratioAsPercent(scope.chanceToRecoverCost)} recover cost.` : `P50 ${money(scope.typicalOpeningPerPack)} · Distribution mean / break-even ${money(scope.averageModelBreakEvenPerPack)} · logarithmic value geometry.`}</p></div> : <p className="mt-5 text-sm text-[var(--text-secondary)]">The canonical P01-P99 percentile curve is unavailable.</p>}
    {packs.length ? <div className="mt-5 border-t border-[var(--ex-line)] pt-4"><p className="text-[.65rem] uppercase tracking-wide text-[var(--text-secondary)]">Sets represented in this model</p><div className="mt-2 flex h-14 gap-1.5 overflow-hidden opacity-70">{packs.map(({target,fallback})=><span key={target.set_id || target.target_id} title={target.name} className="flex h-14 min-w-0 flex-1 items-center justify-center">{fallback ? <Image src={fallback} width={52} height={36} alt="" className="h-9 w-full object-contain" /> : <i className="h-3 w-3 rotate-45 border border-[rgb(var(--ex-teal))]" />}</span>)}</div></div>:null}
  </section>;
}

/* ---------------------------------------------------------------- header --- */

function Header({ scope, marketDate }) {
  return (
    <header className="mb-4">
      <h2 className="text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">
        Pokémon Opening Economics
      </h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        All modeled sealed products normalized per pack.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
        <span className="tabular-nums">{scope.setCount} modeled sets</span>
        <span aria-hidden="true" className="opacity-40">·</span>
        <span className="tabular-nums">{scope.productFamilyCount} represented product families</span>
        <span aria-hidden="true" className="opacity-40">·</span>
        <span className="tabular-nums">{scope.productSkuCount} modeled products</span>
        {marketDate ? (
          <>
            <span aria-hidden="true" className="opacity-40">·</span>
            <span className="tabular-nums">As of {marketDate}</span>
          </>
        ) : null}
      </div>
    </header>
  );
}

/* -------------------------------------------------------------- equation --- */

/**
 * Modeled Return and Entertainment Cost are two readings of one split, so they
 * share a surface and a single bar rather than sitting in separate cards.
 */
function EconomicEquation({ scope }) {
  const returned = centsPerDollar(scope.modeledReturnOnSpend);
  const kept = returned === null ? null : 100 - returned;
  const returnPercent = ratioAsPercent(scope.modeledReturnOnSpend);
  const costPercent = ratioAsPercent(scope.entertainmentCostShare);

  return (
    <section className={`${styles.surface} rounded-xl p-4 sm:p-5`} data-opening-economics-equation>
      <div className="grid gap-4 sm:grid-cols-2 sm:gap-0">
        <div className="sm:pr-5">
          <div className="flex items-center gap-1.5">
            <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              Modeled Return on Spend
            </h3>
            <InfoPopover text="Long-run modeled gross card-market value relative to spend across every eligible modeled sealed product after verified per-pack normalization and hierarchical weighting." />
          </div>
          <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight text-[var(--text-primary)]">
            {returnPercent ?? <Dash />}
          </p>
          {returned !== null ? (
            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
              About <strong className="tabular-nums text-[var(--text-primary)]">{returned}¢</strong> of modeled gross
              card value for every $1 spent opening packs.
            </p>
          ) : null}
        </div>

        <div className={`${local.equationRule} sm:pl-5`}>
          <div className="flex items-center gap-1.5">
            <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              Average Entertainment Cost
            </h3>
            <InfoPopover text="The difference between the current cost of a sealed product and the model's long-run Expected Value of the cards inside it. Opening converts a sealed asset into its contents; this estimates the modeled economic value given up in exchange for that opening experience." />
          </div>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="text-3xl font-semibold tabular-nums tracking-tight text-[var(--text-primary)]">
              {money(scope.averageEntertainmentCostPerPack) ?? <Dash />}
            </span>
            <span className="text-xs text-[var(--text-secondary)]">per pack</span>
          </p>
          {kept !== null ? (
            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
              About <strong className="tabular-nums text-[var(--text-primary)]">{kept}¢</strong> of every $1 is the
              modeled cost of the opening experience.
            </p>
          ) : null}
        </div>
      </div>

      {returned !== null ? (
        <div className="mt-4">
          <div
            className={local.equationSplit}
            role="img"
            aria-label={`Of every dollar spent, about ${returned} cents returns as modeled card value and about ${kept} cents is entertainment cost.`}
          >
            <span className={local.equationReturned} style={{ width: `${returned}%` }} />
            <span className={local.equationCost} style={{ width: `${kept}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-[0.68rem] text-[var(--text-secondary)]">
            <span>{returnPercent} returned as card value</span>
            <span>{costPercent} entertainment cost</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/* --------------------------------------------------------------- descent --- */

/**
 * The signature element: how far a pack's price falls to its typical outcome.
 * Bar length is the value as a share of the pack price, so the collapse reads
 * as distance rather than as three numbers the reader must compare themselves.
 */
function ValueDescent({ scope }) {
  const stages = valueDescent(scope);
  if (!stages) return null;

  return (
    <section className={`${styles.surface} mt-3 rounded-xl p-4 sm:p-5`} data-opening-economics-descent>
      <div className="flex items-center gap-1.5">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">From price to typical opening</h3>
        <InfoPopover text="Model Break-Even is the modeled Expected Value expressed as a purchase price — the price at which long-run modeled value would equal cost. It is the same statistic as Expected Value, not a second one." />
      </div>

      <ol className="mt-3.5 space-y-3">
        {stages.map((stage) => (
          <li key={stage.key} data-descent-stage={stage.key}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-xs text-[var(--text-secondary)]">{stage.label}</span>
              <span className="text-lg font-semibold tabular-nums text-[var(--text-primary)]">
                {stage.value ?? <Dash />}
              </span>
            </div>
            <div className={`${local.descentTrack} mt-1.5`}>
              {stage.percent === null ? null : (
                <div
                  className={`${local.descentFill} ${stage.key === "price" ? local.descentFillReference : ""}`}
                  style={{ width: `${Math.min(100, stage.percent)}%` }}
                />
              )}
            </div>
            <p className="mt-1 text-[0.68rem] text-[var(--text-secondary)]">{stage.note}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* --------------------------------------------------------------- insight --- */

function EvInsight({ scope }) {
  const ev = money(scope.averageModelBreakEvenPerPack);
  const p75 = money(scope.valuePerPackPercentiles?.p75);
  if (!ev || !p75) return null;
  return (
    <section className={`${local.insight} mt-3 p-3.5`} data-opening-economics-insight>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]">
        Why Expected Value can feel misleading
      </h3>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">
        The model&apos;s long-run average of <strong className="tabular-nums text-[var(--text-primary)]">{ev}</strong>{" "}
        sits above the 75th percentile opening of{" "}
        <strong className="tabular-nums text-[var(--text-primary)]">{p75}</strong>. Rare high-value outcomes pull
        Expected Value substantially above what most modeled openings return, so the average describes the long run
        rather than a typical result.
      </p>
    </section>
  );
}

/* ----------------------------------------------------------------- range --- */

/**
 * Percentile ticks and one EV marker on a logarithmic axis. The scale is
 * labeled rather than left to be inferred, and the gaps between ticks are
 * never filled with a curve — nothing between two published percentiles is
 * measured.
 */
function OutcomeRange({ scope }) {
  const range = outcomeRangePositions(scope.valuePerPackPercentiles, scope.averageModelBreakEvenPerPack);
  if (!range) return null;

  const p05 = range.points.find((point) => point.key === "p05");
  const p75 = range.points.find((point) => point.key === "p75");
  const textual = range.points.map((point) => `${point.label}, ${point.display}`).join("; ");

  return (
    <section className={`${styles.surface} mt-3 rounded-xl p-4 sm:p-5`} data-opening-economics-distribution>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Opening outcome range</h3>
          <InfoPopover text="Six measured points from the pooled modeled outcomes of every participating set. A percentile is a position in that distribution, not a probability: the 95th percentile is the value only 5% of modeled openings exceed." />
        </div>
        <span className="text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)]">
          Logarithmic scale
        </span>
      </div>

      <div className="mt-6 px-1">
        <div
          className={`${local.rangeAxis} relative`}
          role="img"
          aria-label={`Pooled opening outcomes on a logarithmic scale. ${textual}. Expected Value ${range.expectedValue?.display ?? "unavailable"}.`}
        >
          {p05 && p75 ? (
            <span
              className={local.rangeTypicalBand}
              style={{ left: `${p05.percent}%`, width: `${Math.max(1, p75.percent - p05.percent)}%` }}
            />
          ) : null}
          {range.points.map((point) => (
            <span
              key={point.key}
              className={`${local.rangeTick} ${point.typical ? local.rangeTickTypical : ""}`}
              style={{ left: `${point.percent}%` }}
              data-range-tick={point.key}
            />
          ))}
          {range.expectedValue ? (
            <span
              className={local.rangeMarker}
              style={{ left: `${range.expectedValue.percent}%` }}
              data-range-marker="expectedValue"
            />
          ) : null}
        </div>

        {/* A LEGEND, not axis labels. P05, P25 and P50 sit within about ten
            percent of the axis, so labels anchored under their own ticks would
            overlap and clip. An evenly spaced row beneath a log axis would
            imply an alignment that is not there, so it is captioned as a value
            list and separated from the axis by a rule. */}
        <p className="mt-5 border-t border-[var(--ex-line)] pt-2.5 text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">
          Value at each percentile
        </p>
        <ul className="mt-2 grid grid-cols-3 gap-x-3 gap-y-2 sm:grid-cols-6">
          {range.points.map((point) => (
            <li key={point.key}>
              <div
                className={`text-[0.65rem] uppercase tracking-wide ${
                  point.typical ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                }`}
              >
                {point.shortLabel}
              </div>
              <div
                className={`mt-0.5 tabular-nums ${
                  point.typical
                    ? "text-sm font-semibold text-[var(--text-primary)]"
                    : "text-xs text-[var(--text-secondary)]"
                }`}
              >
                {point.display}
              </div>
            </li>
          ))}
        </ul>

        {range.expectedValue ? (
          <p className="mt-3 border-t border-[var(--ex-line)] pt-2.5 text-xs text-[var(--text-secondary)]">
            <span aria-hidden="true" className="mr-1.5 inline-block h-2 w-2 rotate-45 bg-[var(--text-primary)]" />
            Expected Value <strong className="tabular-nums text-[var(--text-primary)]">
              {range.expectedValue.display}
            </strong>{" "}
            sits to the right of the shaded band holding most modeled openings.
          </p>
        ) : null}
      </div>
    </section>
  );
}

/* --------------------------------------------------------- tier 3 metrics --- */

function SupportingMetrics({ scope }) {
  const items = [
    {
      key: "typicalRetention",
      label: "Typical Retention",
      value: ratioAsPercent(scope.typicalRetention),
      note: "The median modeled opening returns about this share of its purchase price in gross card value.",
      help: "Typical Retention is the MEDIAN outcome relative to purchase price. Modeled Return on Spend is the long-run aggregate Expected Value relative to aggregate spend. The two answer different questions and are not interchangeable.",
    },
    {
      key: "chanceToRecover",
      label: "Chance to Recover Cost",
      value: ratioAsPercent(scope.chanceToRecoverCost),
      note: "How often a modeled opening reaches or exceeds what the pack cost.",
      help: "The modeled probability that an opening's card value reaches or exceeds the current pack price for its set.",
    },
  ];
  return (
    <section className="mt-3 grid gap-3 sm:grid-cols-2" data-opening-economics-supporting>
      {items.map((item) => (
        <div key={item.key} className={`${styles.surfaceQuiet} rounded-xl p-3.5`} data-supporting-metric={item.key}>
          <div className="flex items-center gap-1.5">
            <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">{item.label}</h3>
            <InfoPopover text={item.help} />
          </div>
          <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
            {item.value ?? <Dash />}
          </p>
          <p className="mt-1 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">{item.note}</p>
        </div>
      ))}
    </section>
  );
}

/* ------------------------------------------------------------ era preview --- */

function EraPreview({ eras, onSelectEras }) {
  if (!Array.isArray(eras) || eras.length === 0) return null;
  return (
    <section className={`${styles.surface} mt-3 rounded-xl p-4 sm:p-5`} data-opening-economics-era-preview>
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">How eras compare</h3>
      <ul className="mt-2">
        {eras.map((era) => (
          <li key={era.eraName} className={`${local.eraRow} py-3`}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium text-[var(--text-primary)]">{era.eraName}</span>
              <span className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
                {era.setCount} sets
              </span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
              {[
                ["Modeled Return", ratioAsPercent(era.modeledReturnOnSpend), true],
                ["Entertainment Cost", money(era.averageEntertainmentCostPerPack), false],
                ["Typical Opening", money(era.typicalOpeningPerPack), false],
                ["Typical Retention", ratioAsPercent(era.typicalRetention), false],
              ].map(([label, value, strong]) => (
                <div key={label}>
                  <dt className="text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">{label}</dt>
                  <dd
                    className={`mt-0.5 tabular-nums ${
                      strong
                        ? "text-base font-semibold text-[var(--text-primary)]"
                        : "text-sm text-[var(--text-primary)]"
                    }`}
                  >
                    {value ?? <Dash />}
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
      {onSelectEras ? (
        <button
          type="button"
          onClick={onSelectEras}
          data-view-era-details
          className="mt-3 text-xs font-medium text-[rgb(var(--ex-teal))] underline-offset-2 hover:underline"
        >
          Compare all eras →
        </button>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------ empty states --- */

/**
 * A published snapshot that predates the aggregate methodology is NOT an error.
 * It is reported as a plain, restrained absence, separately from a genuine
 * request failure, and it never falls back to reconstructing the figures.
 */
export function OpeningEconomicsEmpty({ economics, title, subject }) {
  const failed = economics?.reason === "request_failed" || economics?.reason === "backend_error";
  return (
    <section className={`${styles.surface} rounded-xl p-5`} data-opening-economics-unavailable>
      <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
      <p className="mt-1.5 max-w-prose text-sm text-[var(--text-secondary)]">
        {failed
          ? `${subject} could not be loaded. The other ranking views are unaffected.`
          : `The current published snapshot does not yet contain aggregate ${subject.toLowerCase()}.`}
      </p>
    </section>
  );
}

export function OpeningEconomicsSkeleton() {
  return (
    <section aria-busy="true" aria-label="Loading opening economics" data-opening-economics-skeleton>
      <div className={`${local.skeleton} h-7 w-64`} />
      <div className={`${local.skeleton} mt-2 h-4 w-80 max-w-full`} />
      <div className={`${styles.surface} mt-4 rounded-xl p-5`}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className={`${local.skeleton} h-16`} />
          <div className={`${local.skeleton} h-16`} />
        </div>
        <div className={`${local.skeleton} mt-4 h-1.5`} />
      </div>
      <div className={`${styles.surface} mt-3 rounded-xl p-5`}>
        <div className={`${local.skeleton} h-[7.5rem]`} />
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ page --- */

export default function OpeningEconomicsOverall({ economics, onSelectEras = null, targets = [] }) {
  if (economics?.status === "loading") return <OpeningEconomicsSkeleton />;
  if (!isAvailable(economics)) {
    return (
      <OpeningEconomicsEmpty
        economics={economics}
        title="Pokémon Opening Economics"
        subject="Opening Economics"
      />
    );
  }

  const scope = economics.global;

  return (
    <section data-opening-economics-overall>
      <Header scope={scope} marketDate={economics.marketDate} />
      <OpeningDistribution scope={scope} targets={targets} />
      <EraPreview eras={economics.eras} onSelectEras={onSelectEras} />

      <details className={`${styles.surfaceQuiet} mt-3 rounded-xl px-4 py-3`} data-opening-economics-methodology>
        <summary className="cursor-pointer list-none text-xs font-medium text-[var(--text-primary)]">
          How this is calculated
        </summary>
        <ul className="mt-2.5 space-y-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
          {METHODOLOGY.map((line) => (
            <li key={line} className="flex gap-2">
              <span aria-hidden="true" className="mt-1.5 h-1 w-1 flex-none rounded-full bg-[rgb(var(--ex-teal))]" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </details>

      <p className="mt-3 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">
        Card values reflect modeled gross market value. Selling fees, shipping, liquidity, grading costs, and other
        transaction costs are not deducted.
      </p>
    </section>
  );
}
