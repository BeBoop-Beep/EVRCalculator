"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import RipDistributionChart from "@/components/explore/RipDistributionChart";

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

function normalizeScore(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed >= 0 && parsed <= 1 ? parsed * 100 : parsed;
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
  const normalized = normalizeScore(value);
  return normalized === null ? "—" : normalized.toFixed(1);
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

function getVerdictLabel(summary) {
  const packScore = normalizeScore(summary?.pack_score);
  const roiPercent = toNumber(summary?.roi_percent);
  const probProfit = normalizeProbability(summary?.prob_profit);
  const stabilityScore = normalizeScore(summary?.stability_score);

  if (packScore === null || roiPercent === null || probProfit === null || stabilityScore === null) {
    return "—";
  }

  if (packScore >= 80 && roiPercent >= 15 && probProfit >= 0.6) {
    return "Strong Rip";
  }
  if (packScore >= 65 && stabilityScore >= 60 && probProfit >= 0.5) {
    return "Balanced Rip";
  }
  if (packScore >= 55 && stabilityScore < 45 && probProfit >= 0.35) {
    return "Chase Heavy";
  }
  if (packScore < 45 || roiPercent < 0) {
    return "Poor EV";
  }
  if (stabilityScore < 45 || probProfit < 0.35) {
    return "Risky Rip";
  }
  return "Balanced Rip";
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

function getScoreRankContext(targets, selectedTargetId, scoreKey) {
  const scoredRows = (Array.isArray(targets) ? targets : [])
    .map((target) => ({
      targetId: String(target?.target_id || ""),
      score: normalizeScore(target?.[scoreKey]),
    }))
    .filter((row) => row.targetId && row.score !== null)
    .sort((left, right) => right.score - left.score);

  if (scoredRows.length === 0) {
    return null;
  }

  const index = scoredRows.findIndex((row) => row.targetId === String(selectedTargetId || ""));
  if (index < 0) {
    return null;
  }

  const rank = index + 1;
  const total = scoredRows.length;
  const topPercent = (rank / total) * 100;
  const relativeScore = total > 1 ? ((total - rank) / (total - 1)) * 100 : 100;

  return {
    rank,
    total,
    topPercent,
    relativeScore,
  };
}

function RankChip({ context }) {
  if (!context) {
    return (
      <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]">
        Rank unavailable
      </span>
    );
  }

  return (
    <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]">
      Rank #{context.rank} of {context.total} • Top {context.topPercent.toFixed(0)}%
    </span>
  );
}

function ScoreMeter({ score }) {
  const normalized = normalizeScore(score);
  const width = normalized === null ? 0 : Math.max(0, Math.min(100, normalized));
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-page)]">
      <div className="h-full rounded-full bg-[var(--brand)]" style={{ width: `${width}%` }} />
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

function ScorePillarCard({ title, score, rankContext, scoreMode, signals, contextMetrics }) {
  const displayedScore =
    scoreMode === "relative" && rankContext
      ? formatRawScore(rankContext.relativeScore)
      : formatScore(score);

  const scoreLabel = scoreMode === "relative" && rankContext ? "Relative" : "Absolute";

  return (
    <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6" title="Related signals, not exact formula inputs.">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h3>
          <p className="mt-1 text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">{scoreLabel} score</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-right">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Score</p>
          <p className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">{displayedScore}</p>
        </div>
      </div>

      <ScoreMeter score={scoreMode === "relative" && rankContext ? rankContext.relativeScore : score} />

      <div className="mt-3 flex flex-wrap gap-2">
        <RankChip context={rankContext} />
        <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]" title="These metrics are related context signals.">
          Related signals
        </span>
      </div>

      <div className="mt-4 space-y-1">
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
  const rankings = explorePayload?.rankings || [];
  const ripStatistics = explorePayload?.rip_statistics;
  const warnings = [
    ...(targetsPayload?.meta?.warnings || []),
    ...(explorePayload?.meta?.warnings || []),
  ];

  const selectedName = selectedTarget?.name || requestedTargetId || "Selected Set";
  const verdictLabel = getVerdictLabel(summary);
  const percentileP5 = getPercentileValue(percentiles, 5);
  const percentileP25 = getPercentileValue(percentiles, 25);
  const percentileP50 = getPercentileValue(percentiles, 50);
  const percentileP75 = getPercentileValue(percentiles, 75);
  const percentileP90 = getPercentileValue(percentiles, 90);
  const percentileP95 = getPercentileValue(percentiles, 95);
  const percentileP99 = getPercentileValue(percentiles, 99);

  const packContext = useMemo(
    () => getScoreRankContext(targets, requestedTargetId, "pack_score"),
    [targets, requestedTargetId]
  );
  const profitContext = useMemo(
    () => getScoreRankContext(targets, requestedTargetId, "profit_score"),
    [targets, requestedTargetId]
  );
  const safetyContext = useMemo(
    () => getScoreRankContext(targets, requestedTargetId, "safety_score"),
    [targets, requestedTargetId]
  );
  const stabilityContext = useMemo(
    () => getScoreRankContext(targets, requestedTargetId, "stability_score"),
    [targets, requestedTargetId]
  );

  const hasRelativeContext = Boolean(packContext && profitContext && safetyContext && stabilityContext);
  const [scoreMode, setScoreMode] = useState(hasRelativeContext ? "relative" : "absolute");

  useEffect(() => {
    if (!hasRelativeContext && scoreMode !== "absolute") {
      setScoreMode("absolute");
    }
  }, [hasRelativeContext, scoreMode]);

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

  const displayedPackScore =
    scoreMode === "relative" && packContext
      ? formatRawScore(packContext.relativeScore)
      : formatScore(summary.pack_score);

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
                  <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]">
                    Verdict: <span className="ml-1 font-semibold text-[var(--text-primary)]">{verdictLabel}</span>
                  </span>
                  <RankChip context={packContext} />
                </div>

                <div className="mx-auto mt-5 w-full max-w-sm rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-6 py-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_12px_32px_rgba(0,0,0,0.35)]">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]" title="Relative uses live cross-set context from loaded targets. Absolute uses the persisted score value.">
                    {scoreMode === "relative" ? "Relative" : "Absolute"} Pack Score
                  </p>
                  <p className="mt-1 text-[clamp(2.2rem,7vw,3.3rem)] font-semibold leading-none text-[var(--text-primary)]">{displayedPackScore}</p>
                  <ScoreMeter score={scoreMode === "relative" && packContext ? packContext.relativeScore : summary.pack_score} />
                  {hasRelativeContext ? (
                    <div className="mt-4 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-0.5">
                      <button
                        type="button"
                        onClick={() => setScoreMode("relative")}
                        aria-pressed={scoreMode === "relative"}
                        className={`min-w-[6rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
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
                        className={`min-w-[6rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
                          scoreMode === "absolute"
                            ? "bg-[var(--brand)] text-white"
                            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                        }`}
                      >
                        Absolute
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </section>

            <section>
              <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">Score Pillars</h2>
              <div className="grid gap-4 lg:grid-cols-3">
                <ScorePillarCard
                  title="Profit"
                  score={summary.profit_score}
                  rankContext={profitContext}
                  scoreMode={scoreMode}
                  signals={[
                    { label: "EV / Mean Value", value: formatCurrency(summary.mean_value) },
                    {
                      label: "Median-to-Cost Ratio",
                      value:
                        toNumber(summary.median_value) !== null && toNumber(summary.pack_cost) !== null && toNumber(summary.pack_cost) !== 0
                          ? formatNumber(toNumber(summary.median_value) / toNumber(summary.pack_cost), 2)
                          : "—",
                    },
                    { label: "P95-to-Cost Ratio", value: formatNumber(summary.p95_value_to_cost_ratio, 2) },
                    { label: "Probability of Profit", value: formatPercent(summary.prob_profit, { probability: true }) },
                  ]}
                  contextMetrics={[
                    { label: "ROI", value: formatPercent(summary.roi_percent) },
                    { label: "Pack Cost", value: formatCurrency(summary.pack_cost) },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={summary.safety_score}
                  rankContext={safetyContext}
                  scoreMode={scoreMode}
                  signals={[
                    { label: "Expected Loss When Losing", value: formatCurrency(summary.expected_loss_when_losing) },
                    { label: "Median Loss When Losing", value: formatCurrency(summary.median_loss_when_losing) },
                    { label: "Tail Value P5", value: formatCurrency(summary.tail_value_p05) },
                    { label: "Expected Loss Per Pack", value: formatCurrency(summary.expected_loss_per_pack) },
                  ]}
                  contextMetrics={[
                    { label: "Probability of Profit", value: formatPercent(summary.prob_profit, { probability: true }) },
                  ]}
                />
                <ScorePillarCard
                  title="Stability"
                  score={summary.stability_score}
                  rankContext={stabilityContext}
                  scoreMode={scoreMode}
                  signals={[
                    { label: "Coefficient of Variation", value: formatNumber(summary.coefficient_of_variation, 2) },
                    { label: "HHI EV Concentration", value: formatNumber(summary.hhi_ev_concentration, 3) },
                    { label: "Effective Chase Count", value: formatNumber(summary.effective_chase_count, 2) },
                    {
                      label: "Top1 / Top3 / Top5 EV Share",
                      value: `${formatPercent(summary.top1_ev_share)} / ${formatPercent(summary.top3_ev_share)} / ${formatPercent(summary.top5_ev_share)}`,
                    },
                  ]}
                  contextMetrics={[]}
                />
              </div>
            </section>

            <SectionCard title="Outcome Distribution" subtitle="See how simulated pack outcomes are distributed across value ranges.">
              <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
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
