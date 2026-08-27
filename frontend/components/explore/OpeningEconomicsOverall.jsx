"use client";

import React from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import styles from "./explore.module.css";
import {
  UNAVAILABLE_LABEL,
  centsPerDollar,
  distributionRows,
  headlineMetrics,
  isAvailable,
  money,
  ratioAsPercent,
} from "./openingEconomicsSelector.mjs";

/**
 * The Overall lens: what opening a Pokemon pack looks like across every set
 * inDex currently models.
 *
 * Every number rendered here is read straight from the published snapshot.
 * Nothing on this page is calculated in the browser — see
 * openingEconomicsSelector.mjs for why that boundary matters.
 */

function Unavailable({ label = UNAVAILABLE_LABEL }) {
  return <span className="text-[var(--text-secondary)] opacity-70">{label}</span>;
}

function MetricTile({ metric }) {
  return (
    <div className={`${styles.surface} rounded-xl p-3.5`} data-opening-economics-metric={metric.key}>
      <div className="flex items-start gap-1.5">
        <span className="text-[0.7rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          {metric.label}
        </span>
        {metric.help ? <InfoPopover text={metric.help} /> : null}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
          {metric.value ?? <Unavailable />}
        </span>
        {metric.value && metric.suffix ? (
          <span className="text-xs text-[var(--text-secondary)]">{metric.suffix}</span>
        ) : null}
      </div>
      {metric.value && metric.secondary ? (
        <div className="mt-0.5 text-xs tabular-nums text-[var(--text-secondary)]">{metric.secondary}</div>
      ) : null}
    </div>
  );
}

/**
 * The pooled opening distribution.
 *
 * Bars are scaled LINEARLY against the largest published percentile. The
 * resulting shape — four short bars then two long ones — is the actual skew of
 * the modeled population, not a rendering artifact, and it is the clearest way
 * to show that the mean sits far above the median. No curve is drawn and no
 * distribution family is implied: these are six measured points from an
 * empirical population, and the space between them is not interpolated.
 */
function PooledDistribution({ scope }) {
  const rows = distributionRows(scope?.rawDistribution, (value) => money(value));
  if (!rows) return null;
  const max = rows.reduce((largest, row) => (row.raw !== null && row.raw > largest ? row.raw : largest), 0);
  const expectedValue = Number(scope?.expectedValue);
  const evPercent = Number.isFinite(expectedValue) && max > 0
    ? Math.min(100, (expectedValue / max) * 100)
    : null;

  return (
    <section className={`${styles.surface} mt-4 rounded-xl p-4`} data-opening-economics-distribution>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Pooled opening distribution</h3>
        <p className="text-xs text-[var(--text-secondary)]">
          Every modeled opening from every participating set, pooled with each set weighted equally.
        </p>
      </div>
      <ul className="mt-3 space-y-1.5">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center gap-3" data-distribution-point={row.key}>
            <span className="w-9 shrink-0 text-[0.7rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              {row.label}
            </span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--text-secondary)_18%,transparent)]">
              {row.raw !== null && max > 0 ? (
                <span
                  className="block h-full rounded-full bg-[var(--accent,#2dd4bf)]"
                  style={{ width: `${Math.max(1.5, (row.raw / max) * 100)}%` }}
                />
              ) : null}
            </span>
            <span className="w-16 shrink-0 text-right text-xs tabular-nums text-[var(--text-primary)]">
              {row.display ?? <Unavailable label="—" />}
            </span>
          </li>
        ))}
      </ul>
      {evPercent !== null ? (
        <p className="mt-3 border-t border-[color-mix(in_srgb,var(--text-secondary)_16%,transparent)] pt-2.5 text-xs text-[var(--text-secondary)]">
          Expected Value is <strong className="text-[var(--text-primary)]">{money(expectedValue)}</strong> — above the
          75th percentile. A small number of very large openings pull the average far above the typical result, which is
          why Typical Opening and Expected Value answer different questions.
        </p>
      ) : null}
    </section>
  );
}

function EraPreview({ eras, onSelectEras }) {
  if (!Array.isArray(eras) || eras.length === 0) return null;
  return (
    <section className={`${styles.surface} mt-4 rounded-xl p-4`} data-opening-economics-era-preview>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">By era</h3>
        {onSelectEras ? (
          <button
            type="button"
            onClick={onSelectEras}
            className="text-xs font-medium text-[var(--accent,#2dd4bf)] underline-offset-2 hover:underline"
            data-view-era-details
          >
            View era details →
          </button>
        ) : null}
      </div>
      <div className={`${styles.scrollShell} mt-3`}>
        <table className={`${styles.table} w-full text-sm`}>
          <thead>
            <tr>
              <th scope="col" className="text-left">Era</th>
              <th scope="col" className="text-right">Sets</th>
              <th scope="col" className="text-right">Modeled Return</th>
              <th scope="col" className="text-right">Typical Retention</th>
              <th scope="col" className="text-right">Chance to Recover</th>
              <th scope="col" className="text-right">Ent. Cost / Pack</th>
            </tr>
          </thead>
          <tbody>
            {eras.map((era) => (
              <tr key={era.eraName} className={styles.row}>
                <th scope="row" className="text-left font-medium text-[var(--text-primary)]">{era.eraName}</th>
                <td className={`${styles.numeric} text-right`}>{era.setCount ?? <Unavailable label="—" />}</td>
                <td className={`${styles.numeric} text-right`}>{ratioAsPercent(era.modeledReturnOnSpend) ?? <Unavailable label="—" />}</td>
                <td className={`${styles.numeric} text-right`}>{ratioAsPercent(era.typicalOpening?.retention) ?? <Unavailable label="—" />}</td>
                <td className={`${styles.numeric} text-right`}>{ratioAsPercent(era.chanceToBeatCost) ?? <Unavailable label="—" />}</td>
                <td className={`${styles.numeric} text-right`}>{money(era.expectedEntertainmentCost) ?? <Unavailable label="—" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function OpeningEconomicsOverall({ economics, onSelectEras = null }) {
  if (!isAvailable(economics)) {
    return (
      <section className={`${styles.surface} rounded-xl p-6`} data-opening-economics-unavailable>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Pokémon Opening Economics</h2>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          Opening economics are {UNAVAILABLE_LABEL.toLowerCase()} right now. The other ranking views are unaffected.
        </p>
      </section>
    );
  }

  const scope = economics.global;
  const metrics = headlineMetrics(scope);
  const returned = centsPerDollar(scope.modeledReturnOnSpend);
  const kept = returned === null ? null : 100 - returned;

  return (
    <section data-opening-economics-overall>
      <header className="mb-3">
        <h2 className="text-lg font-semibold tracking-tight text-[var(--text-primary)] sm:text-xl">
          Pokémon Opening Economics
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          What opening a Pokémon pack looks like across the sets currently modeled by inDex.
        </p>
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
          Uses one loose booster pack from each of the{" "}
          <strong className="text-[var(--text-primary)]">{scope.setCount}</strong> eligible modeled sets, weighted
          equally, at current tracked market prices
          {economics.marketDate ? ` (${economics.marketDate})` : ""}.{" "}
          <InfoPopover text="Each eligible set contributes exactly one observation — one pack from that set — so no set counts more than another. A loose pack is the only opening unit directly comparable across every modeled set, so booster boxes, ETBs and bundles are analysed in the Products view instead of being averaged in here." />
        </p>
      </header>

      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-3">
        {metrics.map((metric) => (
          <MetricTile key={metric.key} metric={metric} />
        ))}
      </div>

      <section className={`${styles.surfaceQuiet} mt-4 rounded-xl p-4`} data-opening-economics-story>
        <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
          Opening converts a sealed asset into its contents. The gap between what the pack costs and the model&apos;s
          long-run value of those contents is the{" "}
          <strong className="text-[var(--text-primary)]">Entertainment Cost</strong> — the economic price of the opening
          experience.
        </p>
        {returned !== null ? (
          <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
            Across the currently modeled sets, the model returns roughly{" "}
            <strong className="tabular-nums text-[var(--text-primary)]">{returned}¢ in gross card value per $1
            spent</strong>, leaving about{" "}
            <strong className="tabular-nums text-[var(--text-primary)]">{kept}¢ as modeled Entertainment Cost</strong>.
            Expected Value describes the long run, not any single opening — individual results vary enormously, and the
            distribution below shows how far.
          </p>
        ) : null}
      </section>

      <PooledDistribution scope={scope} />
      <EraPreview eras={economics.eras} onSelectEras={onSelectEras} />

      <p className="mt-4 text-xs leading-relaxed text-[var(--text-secondary)]">
        Modeled values use gross tracked card-market value. Selling fees, shipping, liquidity, grading costs, spreads and
        the practical difficulty of liquidating every card are not deducted — so the Entertainment Cost shown here is a
        lower bound on the real economic friction of opening and selling out.
      </p>
    </section>
  );
}
