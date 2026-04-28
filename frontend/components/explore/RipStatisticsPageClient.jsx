"use client";

import { useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import RankBadge from "@/components/ui/RankBadge";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed > 1 ? parsed / 100 : parsed;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : currencyFormatter.format(parsed);
}

function formatPercent(value, options = {}) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  const normalized = options.probability ? normalizeProbability(parsed) * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function formatScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : parsed.toFixed(1);
}

function formatRawScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : parsed.toFixed(1);
}

function formatNumber(value, decimals = 2) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return parsed.toFixed(decimals);
}

function titleCaseStateLabel(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}


function getPercentileValue(percentiles, requestedPercentile) {
  if (!Array.isArray(percentiles)) {
    return null;
  }
  const matched = percentiles.find((entry) => {
    const percentile = toNumber(entry?.percentile);
    if (percentile === null) {
      return false;
    }
    return (
      Math.abs(percentile - requestedPercentile) < 0.001 ||
      Math.abs(percentile - requestedPercentile * 100) < 0.001
    );
  });
  return matched?.value ?? null;
}

function sortObjectEntriesDescending(input) {
  if (!input || typeof input !== "object") {
    return [];
  }
  return Object.entries(input).sort((left, right) => {
    const leftValue = toNumber(left[1]) ?? 0;
    const rightValue = toNumber(right[1]) ?? 0;
    return rightValue - leftValue;
  });
}


function ScoreMeter({ score }) {
  const parsed = Number(score);
  const width = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : 0;
  return (
    <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="h-full rounded-full"
        style={{
          width: `${width}%`,
          background: "linear-gradient(90deg, rgba(20,184,166,0.7) 0%, rgba(94,234,212,0.95) 100%)",
          boxShadow: width > 0 ? "0 0 6px 1px rgba(20,184,166,0.45)" : "none",
        }}
      />
    </div>
  );
}

function MetricRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0 last:pb-0 first:pt-0">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span className="text-sm font-medium text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

function InfoPopover({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label="More info"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] transition-all hover:border-[rgba(20,184,166,0.6)] hover:text-[rgba(20,184,166,0.95)] hover:shadow-[0_0_6px_rgba(20,184,166,0.35)]"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
          <text x="6" y="9" textAnchor="middle" fontSize="7.5" fill="currentColor" fontWeight="600">i</text>
        </svg>
      </button>
      {open ? (
        <div
          role="tooltip"
          className="absolute left-0 top-7 z-20 w-64 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 shadow-[0_8px_32px_rgba(0,0,0,0.45)] text-xs text-[var(--text-secondary)] leading-relaxed"
        >
          {text}
        </div>
      ) : null}
    </div>
  );
}

function ScorePillarCard({ title, score, rankValue, rankTier, signals, contextMetrics, infoText, rankLabel }) {
  const parsedRank = toNumber(rankValue);
  const numericRankTitle = parsedRank === null ? "Rank unavailable" : `${rankLabel} #${Math.round(parsedRank)}`;

  return (
    <article className="flex flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-0.5 text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">Score</p>
          </div>
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
        <div className="flex flex-none flex-col items-end gap-1.5">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-right">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Score</p>
            <p className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">{formatScore(score)}</p>
          </div>
          <RankBadge rank={rankTier} label={rankLabel} title={numericRankTitle} />
        </div>
      </div>

      <ScoreMeter score={score} />

      <div className="mt-4 flex-1 space-y-1">
        {signals.map((metric) => (
          <MetricRow key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>

      {contextMetrics.length > 0 ? (
        <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Context metrics</p>
          <div className="mt-2 space-y-1">
            {contextMetrics.map((metric) => (
              <MetricRow key={metric.label} label={metric.label} value={metric.value} />
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function SectionCard({ title, subtitle, children }) {
  return (
    <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className="mt-4">{children}</div>
    </article>
  );
}

function TopHitRow({ name, evContribution }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3">
      <div
        className="h-10 w-10 flex-none rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel)]"
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[var(--text-primary)]">{name || "Unknown Card"}</p>
      </div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{formatCurrency(evContribution)}</p>
    </div>
  );
}

export default function RipStatisticsPageClient({
  targetsPayload,
  selectedTarget,
  requestedTargetType,
  requestedTargetId,
  explorePayload,
  pageError,
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const targets = targetsPayload?.targets || [];
  const summary = explorePayload?.summary || {};
  const percentiles = explorePayload?.percentiles || [];
  const distributionBins = explorePayload?.distribution_bins || [];
  const thresholdBins = explorePayload?.threshold_bins || [];
  const topHits = explorePayload?.top_hits || [];
  const historyTrend = explorePayload?.history_trend || [];
  const rankings = explorePayload?.rankings || [];
  const ripStatistics = explorePayload?.rip_statistics;
  const warnings = [
    ...(targetsPayload?.meta?.warnings || []),
    ...(explorePayload?.meta?.warnings || []),
  ];

  const selectedName = selectedTarget?.name || requestedTargetId || "Selected Set";
  const percentileP5 = getPercentileValue(percentiles, 5);
  const percentileP25 = getPercentileValue(percentiles, 25);
  const percentileP50 = getPercentileValue(percentiles, 50);
  const percentileP75 = getPercentileValue(percentiles, 75);
  const percentileP90 = getPercentileValue(percentiles, 90);
  const percentileP95 = getPercentileValue(percentiles, 95);
  const percentileP99 = getPercentileValue(percentiles, 99);
  const meanValueToCostRatio = summary.mean_value_to_cost_ratio ?? null;
  const medianValueToCostRatio = summary.median_value_to_cost_ratio ?? null;
  const expectedLossWhenLosingFraction = summary.expected_loss_when_losing_fraction ?? null;
  const medianLossWhenLosingFraction = summary.median_loss_when_losing_fraction ?? null;
  const p05ShortfallToCost = summary.p05_shortfall_to_cost ?? null;

  const [graphMode, setGraphMode] = useState("outcome-distribution");
  const [scoreMode, setScoreMode] = useState("relative");

  const packPathRows = useMemo(
    () => sortObjectEntriesDescending(ripStatistics?.pack_paths),
    [ripStatistics?.pack_paths]
  );
  const normalStateRows = useMemo(
    () => sortObjectEntriesDescending(ripStatistics?.normal_pack_states),
    [ripStatistics?.normal_pack_states]
  );

  const timingRows = Object.entries(explorePayload?.meta?.timings || {}).filter(
    ([, value]) => toNumber(value) !== null
  );

  const chartMarkers = [
    { key: "pack-cost", label: "Pack Cost", value: summary.pack_cost },
    { key: "ev", label: "EV", value: summary.mean_value },
    { key: "median", label: "Median", value: percentileP50 ?? summary.median_value },
    { key: "p5", label: "P5", value: percentileP5 },
    { key: "p25", label: "P25", value: percentileP25 },
    { key: "p75", label: "P75", value: percentileP75 },
    { key: "p90", label: "P90", value: percentileP90 },
    { key: "p95", label: "P95", value: percentileP95 },
    { key: "p99", label: "P99", value: percentileP99 },
    { key: "big-hit", label: "Big Hit", value: summary.big_hit_threshold },
  ];

  const displayedRelativePackScore = formatRawScore(summary.relative_pack_score);
  const displayedAbsolutePackScore = formatRawScore(summary.pack_score);
  const topScoreRaw = scoreMode === "relative" ? summary.relative_pack_score : summary.pack_score;
  const displayedTopScore = scoreMode === "relative" ? displayedRelativePackScore : displayedAbsolutePackScore;

  const displayedProfitScore = scoreMode === "relative" ? summary.relative_profit_score : summary.profit_score;
  const displayedSafetyScore = scoreMode === "relative" ? summary.relative_safety_score : summary.safety_score;
  const displayedStabilityScore =
    scoreMode === "relative" ? summary.relative_stability_score : summary.stability_score;

  const handleTargetChange = (event) => {
    const nextTargetId = String(event.target.value || "").trim();
    if (!nextTargetId) {
      return;
    }
    const nextParams = new URLSearchParams(searchParams?.toString() || "");
    nextParams.set("target_type", "set");
    nextParams.set("target_id", nextTargetId);
    startTransition(() => {
      router.push(`${pathname}?${nextParams.toString()}`);
    });
  };

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6">
        <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 sm:p-5">
          <div className="grid gap-3 md:grid-cols-[11rem_minmax(0,1fr)_auto] md:items-end">
            <div>
              <label htmlFor="rip-statistics-tcg" className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                TCG
              </label>
              <select
                id="rip-statistics-tcg"
                disabled
                value="pokemon"
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)] opacity-80"
              >
                <option value="pokemon">Pokemon</option>
              </select>
            </div>

            <div>
              <label htmlFor="rip-statistics-target" className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                Set
              </label>
              <select
                id="rip-statistics-target"
                value={requestedTargetId || ""}
                onChange={handleTargetChange}
                disabled={isPending || targets.length === 0}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)]"
              >
                {targets.map((target) => (
                  <option key={`${target.target_type}:${target.target_id}`} value={target.target_id}>
                    {target.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="inline-flex h-fit items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]">
              Era: {selectedTarget?.era || "—"}
            </div>
          </div>
        </section>

        {pageError ? (
          <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6">
            <p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p>
            <p className="mt-2 text-sm text-red-300">{pageError}</p>
          </section>
        ) : null}

        {!pageError && explorePayload ? (
          <>
            <section className="page-hero-panel rounded-2xl px-6 py-8">
              <div className="mx-auto max-w-3xl text-center">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">RIP Statistics</p>
                <h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl">{selectedName}</h1>

                <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                  <RankBadge
                    rank={summary.pack_tier}
                    label="Pack Rank"
                    title={
                      summary.pack_rank === null || summary.pack_rank === undefined
                        ? "Pack Rank unavailable"
                        : `Pack rank #${summary.pack_rank}`
                    }
                  />
                </div>

                <div className="mx-auto mt-5 w-full max-w-sm rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-6 py-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_12px_32px_rgba(0,0,0,0.35)]">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                    {scoreMode === "relative" ? "Relative Pack Score" : "Pack Score"}
                  </p>
                  <p className="mt-1 text-[clamp(2.2rem,7vw,3.3rem)] font-semibold leading-none text-[var(--text-primary)]">{displayedTopScore}</p>
                  <ScoreMeter score={topScoreRaw} />

                  <div className="mx-auto mt-4 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                    <button
                      type="button"
                      onClick={() => setScoreMode("relative")}
                      aria-pressed={scoreMode === "relative"}
                      className={`min-w-[7.5rem] rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                        scoreMode === "relative"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      Relative
                    </button>
                    <button
                      type="button"
                      onClick={() => setScoreMode("absolute")}
                      aria-pressed={scoreMode === "absolute"}
                      className={`min-w-[7.5rem] rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                        scoreMode === "absolute"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      Absolute
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <div className="grid gap-4 lg:grid-cols-3">
                <ScorePillarCard
                  title="Profit"
                  score={displayedProfitScore}
                  rankValue={summary.profit_rank}
                  rankTier={summary.profit_tier}
                  rankLabel="Profit Rank"
                  infoText="Profit estimates upside relative to pack cost using simulated value, median-to-cost, and profit probability signals."
                  signals={[
                    { label: "Probability of Profit", value: formatPercent(summary.prob_profit, { probability: true }) },
                    {
                      label: "EV / Mean Value",
                      value: formatNumber(meanValueToCostRatio, 2),
                    },
                    { label: "Median-to-Cost Ratio", value: formatNumber(medianValueToCostRatio, 2) },
                    { label: "P95-to-Cost Ratio", value: formatNumber(summary.p95_value_to_cost_ratio, 2) },
                  ]}
                  contextMetrics={[
                    { label: "ROI", value: formatPercent(summary.roi_percent) },
                    { label: "Pack Cost", value: formatCurrency(summary.pack_cost) },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={displayedSafetyScore}
                  rankValue={summary.safety_rank}
                  rankTier={summary.safety_tier}
                  rankLabel="Safety Rank"
                  infoText="Safety estimates downside protection by looking at expected losses, tail value, and how often packs miss."
                  signals={[
                    { label: "Expected Loss When Losing / Cost", value: formatPercent(expectedLossWhenLosingFraction, { probability: true }) },
                    { label: "Median Loss When Losing / Cost", value: formatPercent(medianLossWhenLosingFraction, { probability: true }) },
                    { label: "P05 Shortfall to Cost", value: formatPercent(p05ShortfallToCost, { probability: true }) },
                  ]}
                  contextMetrics={[
                    { label: "Median Loss When Losing", value: formatCurrency(summary.median_loss_when_losing) },
                    { label: "Tail Value P5", value: formatCurrency(summary.tail_value_p05) },
                  ]}
                />
                <ScorePillarCard
                  title="Stability"
                  score={displayedStabilityScore}
                  rankValue={summary.stability_rank}
                  rankTier={summary.stability_tier}
                  rankLabel="Stability Rank"
                  infoText="Stability estimates how concentrated or volatile outcomes are. Higher stability means returns are less dependent on a tiny number of chase hits."
                  signals={[
                    { label: "Coefficient of Variation", value: formatNumber(summary.coefficient_of_variation, 2) },
                    { label: "HHI EV Concentration", value: formatNumber(summary.hhi_ev_concentration, 3) },
                    { label: "Effective Chase Count", value: formatNumber(summary.effective_chase_count, 2) },
                  ]}
                  contextMetrics={[
                    { label: "Top 1 EV Share", value: formatPercent(summary.top1_ev_share) },
                    { label: "Top 3 EV Share", value: formatPercent(summary.top3_ev_share) },
                    { label: "Top 5 EV Share", value: formatPercent(summary.top5_ev_share) },
                  ]}
                />
              </div>
            </section>

            <SectionCard
              title={graphMode === "historical-trend" ? "Historical Trend" : "Outcome Distribution"}
              subtitle={
                graphMode === "historical-trend"
                  ? "Track how simulated value-to-cost ratios move across daily snapshots."
                  : "See how simulated pack outcomes are distributed across value ranges."
              }
            >
              <div className="mb-4 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                <button
                  type="button"
                  onClick={() => setGraphMode("outcome-distribution")}
                  aria-pressed={graphMode === "outcome-distribution"}
                  className={`min-w-[10.5rem] rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                    graphMode === "outcome-distribution"
                      ? "bg-[var(--brand)] text-white"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  Outcome Distribution
                </button>
                <button
                  type="button"
                  onClick={() => setGraphMode("historical-trend")}
                  aria-pressed={graphMode === "historical-trend"}
                  className={`min-w-[9.5rem] rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                    graphMode === "historical-trend"
                      ? "bg-[var(--brand)] text-white"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  Historical Trend
                </button>
              </div>

              {graphMode === "historical-trend" ? (
                <PackValueHistoryChart historyTrend={historyTrend} />
              ) : (
                <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
              )}

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatTile label="Probability of Profit" value={formatPercent(summary.prob_profit, { probability: true })} />
                <StatTile label="Probability of Big Hit" value={formatPercent(summary.prob_big_hit, { probability: true })} />
                <StatTile label="Max Value" value={formatCurrency(summary.max_value)} />
                <StatTile label="Expected Loss When Losing" value={formatCurrency(summary.expected_loss_when_losing)} />
              </div>
            </SectionCard>

            <section className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-2">
                <SectionCard title="Top Hits" subtitle="Image slot reserved for future payload fields.">
                  <div className="space-y-2">
                    {topHits.length > 0 ? (
                      topHits.map((hit) => (
                        <TopHitRow
                          key={`${hit.card_name || "unknown"}:${hit.ev_contribution || "na"}`}
                          name={hit.card_name}
                          evContribution={hit.ev_contribution}
                        />
                      ))
                    ) : (
                      <p className="text-sm text-[var(--text-secondary)]">No top-hit rows are available.</p>
                    )}
                  </div>
                </SectionCard>

                <SectionCard title="Rarity Pull Contribution" subtitle={null}>
                  <div className="space-y-1">
                    {rankings.length > 0 ? (
                      rankings.map((ranking) => (
                        <MetricRow
                          key={ranking.rarity_bucket}
                          label={titleCaseStateLabel(ranking.rarity_bucket)}
                          value={`${toNumber(ranking.pulled_count)?.toLocaleString("en-US") || "—"} pulls • ${formatCurrency(ranking.avg_sampled_value)}`}
                        />
                      ))
                    ) : (
                      <p className="text-sm text-[var(--text-secondary)]">No rarity ranking rows are available.</p>
                    )}
                  </div>
                </SectionCard>
              </div>

              <SectionCard title="RIP Statistics" subtitle={null}>
                <div className="grid gap-5 md:grid-cols-2">
                  <div>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>
                    <div className="space-y-1">
                      {packPathRows.length > 0 ? (
                        packPathRows.map(([name, count]) => (
                          <MetricRow
                            key={`path:${name}`}
                            label={titleCaseStateLabel(name)}
                            value={toNumber(count)?.toLocaleString("en-US") || "—"}
                          />
                        ))
                      ) : (
                        <p className="text-sm text-[var(--text-secondary)]">No pack-path counts are available.</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Normal States</p>
                    <div className="space-y-1">
                      {normalStateRows.length > 0 ? (
                        normalStateRows.map(([name, count]) => (
                          <MetricRow
                            key={`state:${name}`}
                            label={titleCaseStateLabel(name)}
                            value={toNumber(count)?.toLocaleString("en-US") || "—"}
                          />
                        ))
                      ) : (
                        <p className="text-sm text-[var(--text-secondary)]">No normal-state counts are available.</p>
                      )}
                    </div>
                  </div>
                </div>
              </SectionCard>

              <details className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
                <summary className="cursor-pointer list-none text-lg font-semibold text-[var(--text-primary)]">Advanced Metrics</summary>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <StatTile label="Expected Loss Per Pack" value={formatCurrency(summary.expected_loss_per_pack)} />
                  <StatTile label="Expected Loss When Losing" value={formatCurrency(summary.expected_loss_when_losing)} />
                  <StatTile label="Median Loss When Losing" value={formatCurrency(summary.median_loss_when_losing)} />
                  <StatTile label="Coefficient of Variation" value={formatNumber(summary.coefficient_of_variation, 2)} />
                  <StatTile label="HHI EV Concentration" value={formatNumber(summary.hhi_ev_concentration, 3)} />
                  <StatTile label="Effective Chase Count" value={formatNumber(summary.effective_chase_count, 2)} />
                  <StatTile label="Top 1 EV Share" value={formatPercent(summary.top1_ev_share)} />
                  <StatTile label="Top 3 EV Share" value={formatPercent(summary.top3_ev_share)} />
                  <StatTile label="Top 5 EV Share" value={formatPercent(summary.top5_ev_share)} />
                  <StatTile label="P95 Value / Cost Ratio" value={formatNumber(summary.p95_value_to_cost_ratio, 2)} />
                  <StatTile label="Tail Value P05" value={formatCurrency(summary.tail_value_p05)} />
                </div>
              </details>
            </section>

            {warnings.length > 0 ? (
              <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4 sm:p-5">
                <p className="text-sm font-semibold text-[var(--text-primary)]">Warnings</p>
                <div className="mt-2 space-y-1">
                  {warnings.map((warning, index) => (
                    <p key={`${warning}:${index}`} className="text-sm text-[var(--text-secondary)]">{warning}</p>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Backend Timings</span>
                {timingRows.length > 0 ? (
                  timingRows.map(([key, value]) => (
                    <span
                      key={key}
                      className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-1 text-xs text-[var(--text-secondary)]"
                    >
                      {key.replace(/_/g, " ")}: {toNumber(value)?.toFixed(2)}ms
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-[var(--text-secondary)]">No backend timings are available.</span>
                )}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
