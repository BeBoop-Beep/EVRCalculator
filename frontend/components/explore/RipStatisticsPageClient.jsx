"use client";

import { useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import RankBadge from "@/components/ui/RankBadge";
import { RANK_CONFIG } from "@/constants/rankConfig";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const REQUIRED_PACK_PATHS = ["normal", "demi_god_pack", "god_pack"];

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

function formatPackPathLabel(value) {
  switch (String(value || "").toLowerCase()) {
    case "normal":
      return "Normal";
    case "demi_god_pack":
    case "demi_god":
    case "demigod":
      return "Demi-God Pack";
    case "god_pack":
    case "god":
      return "God Pack";
    default:
      return titleCaseStateLabel(value);
  }
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

function normalizeBarWidth(value, maxValue) {
  const v = toNumber(value);
  const m = toNumber(maxValue);
  if (v === null || m === null || m === 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (v / m) * 100));
}

function withAlpha(color, alpha) {
  if (typeof color !== "string") {
    return null;
  }

  const rgbaMatch = color.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[^)]+)?\)$/i);
  if (!rgbaMatch) {
    return color;
  }

  return `rgba(${rgbaMatch[1]},${rgbaMatch[2]},${rgbaMatch[3]},${alpha})`;
}

function getTierEdgeColor(rankTier) {
  const config = rankTier ? RANK_CONFIG[rankTier] : null;
  if (!config?.color) {
    return null;
  }

  switch (rankTier) {
    case "S":
      return withAlpha(config.color, 0.72);
    case "A":
      return withAlpha(config.color, 0.68);
    case "B":
      return withAlpha(config.color, 0.58);
    case "C":
      return withAlpha(config.color, 0.62);
    case "D":
      return withAlpha(config.color, 0.64);
    case "F":
      return withAlpha(config.color, 0.7);
    default:
      return null;
  }
}

function ScoreMeter({ score, rankTier }) {
  const parsed = Number(score);
  const width = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : 0;
  const edgeColor = getTierEdgeColor(rankTier);
  return (
    <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="relative h-full overflow-hidden rounded-full"
        style={{
          width: `${width}%`,
          background: "linear-gradient(90deg, rgba(20,184,166,0.7) 0%, rgba(94,234,212,0.95) 100%)",
          boxShadow: width > 0 ? "0 0 6px 1px rgba(20,184,166,0.45)" : "none",
        }}
      >
        {edgeColor && width > 0 ? (
          <span
            aria-hidden="true"
            className="absolute inset-y-0 right-0 rounded-r-full"
            style={{
              width: "8%",
              minWidth: "4px",
              maxWidth: "12px",
              background: `linear-gradient(90deg, ${withAlpha(edgeColor, 0)} 0%, ${edgeColor} 100%)`,
              opacity: 0.95,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function HorizontalBar({ widthPercent, nonzeroMin = 2 }) {
  const width = Number.isFinite(widthPercent) ? widthPercent : 0;
  const displayWidth = width > 0 ? Math.max(width, nonzeroMin) : 0;
  return (
    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="h-full rounded-full"
        style={{
          width: `${displayWidth}%`,
          background: "linear-gradient(90deg, rgba(20,184,166,0.55) 0%, rgba(94,234,212,0.85) 100%)",
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
          className="absolute left-0 top-7 z-20 w-64 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-xs leading-relaxed text-[var(--text-secondary)] shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
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
  const flattenedMetrics = [...signals, ...contextMetrics];

  return (
    <article className="flex flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <h3 className="text-base font-semibold tracking-[0.01em] text-[var(--text-secondary)]">{title}</h3>
          <p className="text-2xl font-bold leading-none text-[var(--text-primary)]">{formatScore(score)}</p>
          <RankBadge rank={rankTier} label={rankLabel} title={numericRankTitle} />
        </div>
        <div className="flex flex-none items-center gap-1">
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
      </div>

      <ScoreMeter score={score} rankTier={rankTier} />

      <div className="mt-5 h-px w-full bg-[var(--border-subtle)]" />

      <div className="mt-3 flex-1 space-y-1">
        {flattenedMetrics.map((metric) => (
          <MetricRow key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
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

function TopHitRow({ name, evContribution, evShare, imageSmallUrl, imageLargeUrl }) {
  const imageSrc = imageSmallUrl || imageLargeUrl || null;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3">
      <div className="h-10 w-10 flex-none overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel)]">
        {imageSrc ? <img src={imageSrc} alt={name || "Card"} className="h-full w-full object-cover" /> : null}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[var(--text-primary)]">{name || "Unknown Card"}</p>
        {evShare ? <p className="text-xs text-[var(--text-secondary)]">{evShare} of pack EV</p> : null}
      </div>
      <div className="flex-none text-right">
        <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">EV Contribution</p>
        <p className="text-sm font-semibold text-[var(--text-primary)]">{formatCurrency(evContribution)}</p>
      </div>
    </div>
  );
}

function TopEVDriversContent({ topHits, meanValue }) {
  const hits = Array.isArray(topHits) ? topHits : [];
  const totalEV = toNumber(meanValue);

  if (hits.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No top EV driver rows are available.</p>;
  }

  return (
    <div className="space-y-2">
      {hits.map((hit) => {
        const ev = toNumber(hit?.ev_contribution);
        const evShare = ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null;

        return (
          <TopHitRow
            key={`${hit?.card_name || "unknown"}:${hit?.ev_contribution ?? "na"}`}
            name={hit?.card_name}
            evContribution={hit?.ev_contribution}
            evShare={evShare}
            imageSmallUrl={hit?.image_small_url}
            imageLargeUrl={hit?.image_large_url}
          />
        );
      })}
    </div>
  );
}

function RarityContributionContent({ rankings }) {
  const [mode, setMode] = useState("ev");
  const rows = Array.isArray(rankings) ? rankings : [];

  const evRows = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => (toNumber(b?.total_sampled_value) ?? 0) - (toNumber(a?.total_sampled_value) ?? 0)
    );
    const totalEV = sorted.reduce((sum, row) => sum + (toNumber(row?.total_sampled_value) ?? 0), 0);
    const maxEV = Math.max(...sorted.map((row) => toNumber(row?.total_sampled_value) ?? 0), 0);
    return { sorted, totalEV, maxEV };
  }, [rows]);

  const pullRows = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => (toNumber(b?.pulled_count) ?? 0) - (toNumber(a?.pulled_count) ?? 0)
    );
    const totalPulls = sorted.reduce((sum, row) => sum + (toNumber(row?.pulled_count) ?? 0), 0);
    const maxPulls = Math.max(...sorted.map((row) => toNumber(row?.pulled_count) ?? 0), 0);
    return { sorted, totalPulls, maxPulls };
  }, [rows]);

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No rarity ranking rows are available.</p>;
  }

  return (
    <>
      <div className="mb-4 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
        <button
          type="button"
          onClick={() => setMode("ev")}
          aria-pressed={mode === "ev"}
          className={`rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
            mode === "ev" ? "bg-[var(--brand)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
        >
          EV Contribution
        </button>
        <button
          type="button"
          onClick={() => setMode("pull")}
          aria-pressed={mode === "pull"}
          className={`rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
            mode === "pull" ? "bg-[var(--brand)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
        >
          Pull Frequency
        </button>
      </div>

      {mode === "ev" ? (
        <div className="space-y-3">
          {evRows.maxEV === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No EV contribution data available.</p>
          ) : (
            evRows.sorted.map((ranking) => {
              const value = toNumber(ranking?.total_sampled_value) ?? 0;
              const share = evRows.totalEV > 0 ? `${((value / evRows.totalEV) * 100).toFixed(1)}%` : null;

              return (
                <div key={`ev:${ranking?.rarity_bucket || "unknown"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-[var(--text-secondary)]">{titleCaseStateLabel(ranking?.rarity_bucket)}</span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {formatCurrency(value)}
                      {share ? <span className="ml-1 text-xs text-[var(--text-secondary)]">({share})</span> : null}
                    </span>
                  </div>
                  <HorizontalBar widthPercent={normalizeBarWidth(value, evRows.maxEV)} />
                </div>
              );
            })
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {pullRows.maxPulls === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No pull frequency data available.</p>
          ) : (
            pullRows.sorted.map((ranking) => {
              const count = toNumber(ranking?.pulled_count) ?? 0;
              const share = pullRows.totalPulls > 0 ? `${((count / pullRows.totalPulls) * 100).toFixed(1)}%` : null;

              return (
                <div key={`pull:${ranking?.rarity_bucket || "unknown"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-[var(--text-secondary)]">{titleCaseStateLabel(ranking?.rarity_bucket)}</span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {count.toLocaleString("en-US")}
                      {share ? <span className="ml-1 text-xs text-[var(--text-secondary)]">({share})</span> : null}
                    </span>
                  </div>
                  <HorizontalBar widthPercent={normalizeBarWidth(count, pullRows.maxPulls)} />
                </div>
              );
            })
          )}
        </div>
      )}
    </>
  );
}

function PackPathBars({ packPaths }) {
  const source = typeof packPaths === "object" && packPaths !== null ? packPaths : {};
  const normalized = {
    normal: toNumber(source.normal) ?? 0,
    demi_god_pack: toNumber(source.demi_god_pack ?? source.demi_god ?? source.demigod) ?? 0,
    god_pack: toNumber(source.god_pack ?? source.god) ?? 0,
  };

  const extras = Object.entries(source)
    .filter(([key]) => !["normal", "demi_god_pack", "demi_god", "demigod", "god_pack", "god"].includes(key))
    .map(([key, value]) => ({ key, count: toNumber(value) ?? 0 }));

  const rows = [
    ...REQUIRED_PACK_PATHS.map((key) => ({ key, count: normalized[key] ?? 0 })),
    ...extras,
  ];
  const maxCount = Math.max(...rows.map((row) => row.count), 1);

  return (
    <div className="space-y-3">
      {rows.map(({ key, count }) => (
        <div key={`path:${key}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-[var(--text-secondary)]">{formatPackPathLabel(key)}</span>
            <span className="text-sm font-medium text-[var(--text-primary)]">{count.toLocaleString("en-US")}</span>
          </div>
          <HorizontalBar widthPercent={normalizeBarWidth(count, maxCount)} />
        </div>
      ))}
    </div>
  );
}

function StateBars({ stateRows }) {
  const rows = Array.isArray(stateRows) ? stateRows : [];

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No normal-state counts are available.</p>;
  }

  const maxCount = Math.max(...rows.map(([, value]) => toNumber(value) ?? 0), 1);

  return (
    <div className="space-y-3">
      {rows.map(([name, count]) => {
        const numericCount = toNumber(count) ?? 0;
        return (
          <div key={`state:${name}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-[var(--text-secondary)]">{titleCaseStateLabel(name)}</span>
              <span className="text-sm font-medium text-[var(--text-primary)]">{numericCount.toLocaleString("en-US")}</span>
            </div>
            <HorizontalBar widthPercent={normalizeBarWidth(numericCount, maxCount)} />
          </div>
        );
      })}
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
  const percentileP50 = getPercentileValue(percentiles, 50);
  const percentileP95 = getPercentileValue(percentiles, 95);
  const percentileP99 = getPercentileValue(percentiles, 99);
  const meanValueToCostRatio = summary.mean_value_to_cost_ratio ?? null;
  const medianValueToCostRatio = summary.median_value_to_cost_ratio ?? null;
  const expectedLossWhenLosingFraction = summary.expected_loss_when_losing_fraction ?? null;
  const medianLossWhenLosingFraction = summary.median_loss_when_losing_fraction ?? null;
  const p05ShortfallToCost = summary.p05_shortfall_to_cost ?? null;

  const [graphMode, setGraphMode] = useState("outcome-distribution");
  const [scoreMode, setScoreMode] = useState("relative");

  const normalStateRows = useMemo(
    () => sortObjectEntriesDescending(ripStatistics?.normal_pack_states),
    [ripStatistics?.normal_pack_states]
  );

  const timingRows = Object.entries(explorePayload?.meta?.timings || {}).filter(
    ([, value]) => toNumber(value) !== null
  );

  const chartMarkers = [
    { key: "pack-cost", label: "Pack Cost", value: summary.pack_cost },
    { key: "p5", label: "P5", value: percentileP5 ?? summary.tail_value_p05 },
    { key: "median", label: "Median", value: percentileP50 ?? summary.median_value },
    { key: "p95", label: "P95", value: percentileP95 },
    { key: "p99", label: "P99", value: percentileP99 },
    { key: "big-hit", label: "Big Hit", value: summary.big_hit_threshold },
    { key: "max", label: "Max", value: summary.max_value },
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
    nextParams.set("target_type", requestedTargetType || "set");
    nextParams.set("target_id", nextTargetId);
    startTransition(() => {
      router.push(`${pathname}?${nextParams.toString()}`);
    });
  };

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-8">
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
                <h1 className="mt-2 text-3xl font-semibold text-[var(--text-primary)] sm:text-4xl">{selectedName}</h1>

                <div className="mt-6 flex flex-col items-center gap-1.5">
                  <p className="text-[clamp(3rem,10vw,5rem)] font-semibold leading-tight text-[var(--text-primary)]">{displayedTopScore}</p>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Pack Score</p>
                </div>

                <div className="mx-auto mt-4 w-full max-w-md">
                  <ScoreMeter score={topScoreRaw} rankTier={summary.pack_tier} />
                </div>

                <div className="mt-4 flex justify-center">
                  <RankBadge
                    rank={summary.pack_tier}
                    label="Pack Rank"
                    subtle
                    title={
                      summary.pack_rank === null || summary.pack_rank === undefined
                        ? "Pack Rank unavailable"
                        : `Pack rank #${summary.pack_rank}`
                    }
                  />
                </div>

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
            </section>

            <section className="pt-8">
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
                    { label: "EV / Mean Value", value: formatNumber(meanValueToCostRatio, 2) },
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

            <section className="pt-7">
              <SectionCard
                title={
                  graphMode === "historical-trend"
                    ? "Historical Trend"
                    : graphMode === "pack-breakdown"
                    ? "Pack Breakdown"
                    : "Outcome Distribution"
                }
                subtitle={
                  graphMode === "historical-trend"
                    ? "Track how simulated value-to-cost ratios move across daily snapshots."
                    : graphMode === "pack-breakdown"
                    ? "Inspect pack paths and normal-state counts from simulation runs."
                    : "See how simulated pack outcomes are distributed across value ranges."
                }
              >
                <div className="mb-1.5 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
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
                  <button
                    type="button"
                    onClick={() => setGraphMode("pack-breakdown")}
                    aria-pressed={graphMode === "pack-breakdown"}
                    className={`min-w-[8.5rem] rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                      graphMode === "pack-breakdown"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    Pack Breakdown
                  </button>
                </div>

                {graphMode === "historical-trend" ? (
                  <PackValueHistoryChart historyTrend={historyTrend} />
                ) : graphMode === "pack-breakdown" ? (
                  <div className="grid gap-5 md:grid-cols-2">
                    <div>
                      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>
                      <PackPathBars packPaths={ripStatistics?.pack_paths} />
                    </div>
                    <div>
                      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Normal States</p>
                      <StateBars stateRows={normalStateRows} />
                    </div>
                  </div>
                ) : (
                  <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
                )}

                {graphMode !== "pack-breakdown" ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                    <StatTile label="Probability of Profit" value={formatPercent(summary.prob_profit, { probability: true })} />
                    <StatTile label="Probability of Big Hit" value={formatPercent(summary.prob_big_hit, { probability: true })} />
                    <StatTile label="Median Outcome" value={formatCurrency(percentileP50 ?? summary.median_value)} />
                    <StatTile label="Worst 5% Outcome" value={formatCurrency(percentileP5 ?? summary.tail_value_p05)} />
                    <StatTile label="Max Value" value={formatCurrency(summary.max_value)} />
                  </div>
                ) : null}
              </SectionCard>
            </section>

            <section className="space-y-6 pt-1">
              <div className="grid gap-4 xl:grid-cols-2">
                <SectionCard title="Top EV Drivers" subtitle="These cards contribute the most to expected pack value.">
                  <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} />
                </SectionCard>

                <SectionCard title="Rarity Pull Contribution" subtitle={null}>
                  <RarityContributionContent rankings={rankings} />
                </SectionCard>
              </div>

              <details className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
                <summary className="cursor-pointer list-none text-lg font-semibold text-[var(--text-primary)]">Advanced Metrics</summary>
                <div className="mt-4 space-y-5">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <StatTile label="Expected Loss Per Pack" value={formatCurrency(summary.expected_loss_per_pack)} />
                    <StatTile label="Expected Loss When Losing" value={formatCurrency(summary.expected_loss_when_losing)} />
                    <StatTile label="Median Loss When Losing" value={formatCurrency(summary.median_loss_when_losing)} />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <StatTile label="Coefficient of Variation" value={formatNumber(summary.coefficient_of_variation, 2)} />
                    <StatTile label="HHI EV Concentration" value={formatNumber(summary.hhi_ev_concentration, 3)} />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <StatTile label="P95 Value / Cost Ratio" value={formatNumber(summary.p95_value_to_cost_ratio, 2)} />
                    <StatTile label="Effective Chase Count" value={formatNumber(summary.effective_chase_count, 2)} />
                  </div>
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