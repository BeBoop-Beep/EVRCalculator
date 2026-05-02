"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import InterpretationInsight from "@/components/explore/InterpretationInsight";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import InfoPopover from "@/components/ui/InfoPopover";
import RankBadge from "@/components/ui/RankBadge";
import { RANK_CONFIG } from "@/constants/rankConfig";
import { getFriendlyMetricLabel, getScoreTootip, getFormattedTooltip, getMetricTooltip } from "@/constants/interpretabilityConfig";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const REQUIRED_PACK_PATHS = ["normal", "demi_god_pack", "god_pack"];
const ANALYSIS_SECTION_ID = "explore-outcomes";
const GRAPH_SECTION_KEYS = new Set(["outcome-distribution", "historical-trend", "pack-breakdown"]);
const SECTION_ID_MAP = {
  "pack-score": "explore-score",
  "outcome-distribution": "explore-outcomes",
  "historical-trend": "explore-outcomes",
  "pack-breakdown": "explore-outcomes",
  "top-ev-drivers": "explore-drivers",
  "rarity-contribution": "explore-rarity",
  "advanced-metrics": "explore-advanced",
};

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
  const endColor = edgeColor || "rgba(94,234,212,0.98)";
  const transitionColor = withAlpha(endColor, 0.54);
  const brightEndColor = withAlpha(endColor, 0.74);
  const glowColor = withAlpha(endColor, 0.42);
  return (
    <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="relative h-full overflow-hidden rounded-full"
        style={{
          width: `${width}%`,
          background: `linear-gradient(90deg, rgba(20,184,166,0.66) 0%, rgba(45,212,191,0.82) 50%, ${transitionColor} 85%, ${brightEndColor} 100%)`,
          boxShadow: width > 0 ? `0 0 4px 0px rgba(20,184,166,0.22), inset 0 0 2px ${withAlpha(endColor, 0.12)}` : "none",
        }}
      >
        {width > 0 ? (
          <span
            aria-hidden="true"
            className="absolute top-1/2 right-0 h-1.5 w-1.5 -translate-y-1/2 rounded-full"
            style={{
              background: brightEndColor,
              boxShadow: `0 0 3px ${glowColor}`,
              opacity: 0.9,
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

function MetricRow({ label, value, infoText }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0 last:pb-0 first:pt-0">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="text-sm text-[var(--text-secondary)]">{friendlyLabel}</span>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <span className="text-sm font-medium text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

function ScorePillarCard({
  title,
  score,
  rankValue,
  rankTier,
  signals,
  contextMetrics,
  infoText,
  rankLabel,
  sectionMeta,
  fallbackSummary,
}) {
  const parsedRank = toNumber(rankValue);
  const numericRankTitle = parsedRank === null ? "Rank unavailable" : `${rankLabel} #${Math.round(parsedRank)}`;
  const flattenedMetrics = [...signals, ...contextMetrics];

  return (
    <article className="flex flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <h3 className="text-base font-semibold tracking-[0.01em] text-[var(--text-secondary)]">{title}</h3>
          <p className="text-2xl font-bold leading-none text-[var(--text-primary)]">{formatScore(score)}</p>
          <RankBadge rank={rankTier} label={rankLabel} title={numericRankTitle} size="supporting" subtle />
        </div>
        <div className="flex flex-none items-center gap-1">
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
      </div>

      <ScoreMeter score={score} rankTier={rankTier} />

      <div className="min-h-[140px]">
        <InterpretationInsight
          sectionMeta={sectionMeta}
          fallbackSummary={fallbackSummary}
          compact
          showEvidence={false}
          className="mt-3"
        />
      </div>

      <div className="mt-5 h-px w-full bg-[var(--border-subtle)]" />

      <div className="mt-3 flex-1 space-y-1">
        {flattenedMetrics.map((metric) => (
          <MetricRow
            key={metric.label}
            label={metric.label}
            value={metric.value}
            infoText={getMetricTooltip(metric.label)}
          />
        ))}
      </div>
    </article>
  );
}

function StatTile({ label, value, valueClassName = "text-lg" }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className={`mt-2 font-semibold text-[var(--text-primary)] ${valueClassName}`}>{value}</p>
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

function TopHitRow({ name, evContribution, evShare, imageUrl, imageSmallUrl, imageLargeUrl }) {
  const imageSrc = imageUrl || imageSmallUrl || imageLargeUrl || null;
  const [hasImageError, setHasImageError] = useState(false);

  useEffect(() => {
    setHasImageError(false);
  }, [imageSrc]);

  const shouldRenderImage = Boolean(imageSrc) && !hasImageError;

  return (
    <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3">
      <div className="h-[4.5rem] w-[3.125rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]">
        {shouldRenderImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageSrc}
            alt={name ? `${name} card image` : "Card image"}
            loading="lazy"
            decoding="async"
            onError={() => setHasImageError(true)}
            className="h-full w-full rounded-[5px] object-contain"
          />
        ) : null}
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
  const visibleTopEV = hits.reduce((sum, hit) => sum + (toNumber(hit?.ev_contribution) ?? 0), 0);
  const hasPackTotalEV = totalEV !== null;
  const totalLabel = hasPackTotalEV ? "Total Pack EV" : "Top 10 EV";
  const totalValue = hasPackTotalEV ? totalEV : visibleTopEV;

  if (hits.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No top EV driver rows are available.</p>;
  }

  return (
    <div className="space-y-2">
      <p className="mb-2 text-xs text-[var(--text-secondary)]">
        {totalLabel}: {formatCurrency(totalValue)}
      </p>
      {hits.map((hit) => {
        const ev = toNumber(hit?.ev_contribution);
        const evShare = ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null;

        return (
          <TopHitRow
            key={`${hit?.card_name || "unknown"}:${hit?.ev_contribution ?? "na"}`}
            name={hit?.card_name}
            evContribution={hit?.ev_contribution}
            evShare={evShare}
            imageUrl={hit?.image_url}
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

      <p className="mb-3 text-xs text-[var(--text-secondary)]">
        {mode === "ev"
          ? `Total EV Represented: ${formatCurrency(evRows.totalEV)}`
          : `Total Pull Events: ${pullRows.totalPulls.toLocaleString("en-US")} pulls`}
      </p>

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

function SectionNavigation({ items, activeSection, onSelect, mobile = false }) {
  return (
    <nav aria-label="RIP statistics section navigation" className={mobile ? "space-y-1" : "space-y-1.5"}>
      {items.map((item) => {
        const isActive = activeSection === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            aria-current={isActive ? "location" : undefined}
            className={[
              "group flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left transition-colors",
              isActive
                ? "border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)]"
                : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-subtle)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={[
                  "h-2 w-2 rounded-full transition-colors",
                  isActive ? "bg-[var(--brand)]" : "bg-[var(--border-subtle)] group-hover:bg-[var(--text-secondary)]",
                ].join(" ")}
              />
              <span className={mobile ? "text-sm font-medium" : "text-sm font-medium leading-tight"}>{item.label}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function buildEvidenceMap(sectionMeta) {
  const evidence = Array.isArray(sectionMeta?.evidence) ? sectionMeta.evidence : [];
  const mapping = {};
  evidence.forEach((item) => {
    if (!item?.label) {
      return;
    }
    mapping[String(item.label).toLowerCase()] = item.value;
  });
  return mapping;
}

function getPackBreakdownEvidence(sectionMeta) {
  const evidenceMap = buildEvidenceMap(sectionMeta);
  const rows = [
    ["Dominant path", evidenceMap["dominant path"]],
    ["Dominant path share", evidenceMap["dominant path share"]],
    ["Special path share", evidenceMap["special path share"]],
  ];

  return rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() && String(value) !== "N/A" && String(value) !== "—");
}

function getTopEvEvidence(sectionMeta) {
  const evidenceMap = buildEvidenceMap(sectionMeta);
  const rows = [
    ["Leading card", evidenceMap["leading card"]],
    ["Top card EV share", evidenceMap["top card ev share"]],
    ["Top 3 EV share", evidenceMap["top 3 ev share"]],
    ["Leading value group", evidenceMap["leading value group"]],
  ];

  return rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() && String(value) !== "N/A" && String(value) !== "—");
}

function CompactBottomSectionNav({ activeSection, onSelect }) {
  const items = [
    {
      id: "pack-score",
      label: "Score",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 18.25h15" />
          <path d="M7.5 16v-2.8" />
          <path d="M11.5 16v-5.1" />
          <path d="M15.5 16v-7.3" />
          <path d="M6.9 10.6 10.8 8l3.2 1.9 3.4-3.9" />
          <path d="M15.7 6h2.8v2.8" />
        </svg>
      ),
    },
    {
      id: "outcome-distribution",
      label: "Outcomes",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 18.25h15" />
          <path d="M7.5 14.5v-4" />
          <path d="M11.5 16v-7" />
          <path d="M15.5 12.5V8" />
          <path d="M4.5 8.5h15" />
        </svg>
      ),
    },
    {
      id: "top-ev-drivers",
      label: "Drivers",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 12h3.5l2.1-4.1 4.2 8.2 2.2-4.1H20" />
          <circle cx="13.55" cy="16.1" r="0.85" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
    {
      id: "rarity-contribution",
      label: "Rarity",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 4.5 14.7 9.8l5.8.8-4.2 4.1 1 5.8L12 17.7l-5.3 2.8 1-5.8-4.2-4.1 5.8-.8Z" />
        </svg>
      ),
    },
    {
      id: "advanced-metrics",
      label: "Advanced",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 3.75v3" />
          <path d="M12 17.25v3" />
          <path d="M4.93 6.43 7.05 8.55" />
          <path d="M16.95 18.45 19.07 20.57" />
          <path d="M3.75 12h3" />
          <path d="M17.25 12h3" />
          <path d="M4.93 20.57 7.05 18.45" />
          <path d="M16.95 8.55 19.07 6.43" />
          <circle cx="12" cy="12" r="3.25" />
        </svg>
      ),
    },
  ];

  const isItemActive = (itemId) => {
    if (itemId === "outcome-distribution") {
      return GRAPH_SECTION_KEYS.has(activeSection) || activeSection === ANALYSIS_SECTION_ID;
    }
    return activeSection === itemId;
  };

  return (
    <div className="mx-auto grid max-w-xl grid-cols-5 gap-1 px-3 pt-2">
      {items.map((item) => {
        const isActive = isItemActive(item.id);
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            aria-current={isActive ? "location" : undefined}
            className={[
              "flex flex-col items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-[11px] font-medium transition-colors duration-150 ease-out",
              isActive
                ? "text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span className={["transition-transform duration-150 ease-out", isActive ? "scale-110" : "scale-100"].join(" ")}>
              {item.icon}
            </span>
            <span>{item.label}</span>
          </button>
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
  const interpretation = explorePayload?.interpretation || {};
  const interpretationMeta = interpretation?.meta || {};
  const packScoreMeta = interpretationMeta?.packScore;
  const profitMeta = interpretationMeta?.profit;
  const safetyMeta = interpretationMeta?.safety;
  const stabilityMeta = interpretationMeta?.stability;
  const outcomeDistributionMeta = interpretationMeta?.outcomeDistribution;
  const historicalTrendMeta = interpretationMeta?.historicalTrend;
  const packBreakdownMeta = interpretationMeta?.packBreakdown;
  const topEvDriversMeta = interpretationMeta?.topEvDrivers;
  const rarityContributionMeta = interpretationMeta?.rarityContribution;
  const advancedMetricsMeta = interpretationMeta?.advancedMetrics;

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
  const [activeSection, setActiveSection] = useState("pack-score");
  const [heroSetPickerOpen, setHeroSetPickerOpen] = useState(false);
  const visibleSectionRatiosRef = useRef({});
  const heroSetPickerRef = useRef(null);

  const graphSectionMeta =
    graphMode === "historical-trend"
      ? historicalTrendMeta
      : graphMode === "pack-breakdown"
      ? packBreakdownMeta
      : outcomeDistributionMeta;

  const graphSectionFallback =
    graphMode === "historical-trend"
      ? interpretation?.historicalTrend
      : graphMode === "pack-breakdown"
      ? interpretation?.packBreakdown
      : interpretation?.outcomeDistribution;

  const packBreakdownEvidenceRows = useMemo(
    () => getPackBreakdownEvidence(packBreakdownMeta),
    [packBreakdownMeta]
  );

  const topEvEvidenceRows = useMemo(
    () => getTopEvEvidence(topEvDriversMeta),
    [topEvDriversMeta]
  );

  const normalStateRows = useMemo(
    () => sortObjectEntriesDescending(ripStatistics?.normal_pack_states),
    [ripStatistics?.normal_pack_states]
  );

  const timingRows = Object.entries(explorePayload?.meta?.timings || {}).filter(
    ([, value]) => toNumber(value) !== null
  );

  const sectionNavItems = useMemo(
    () => [
      { id: "pack-score", label: "Pack Score" },
      { id: "outcome-distribution", label: "Outcome Distribution" },
      { id: "historical-trend", label: "Historical Trend" },
      { id: "pack-breakdown", label: "Pack Breakdown" },
      { id: "top-ev-drivers", label: "Top Expected Value (EV) Drivers" },
      { id: "rarity-contribution", label: "Rarity Contribution" },
      { id: "advanced-metrics", label: "Advanced Metrics" },
    ],
    []
  );

  const resolveActiveSection = () => {
    const currentVisibleEntries = Object.entries(visibleSectionRatiosRef.current).filter(([, ratio]) => ratio > 0);
    if (currentVisibleEntries.length === 0) {
      return null;
    }

    currentVisibleEntries.sort((left, right) => right[1] - left[1]);
    const [mostVisibleId] = currentVisibleEntries[0];

    if (mostVisibleId === ANALYSIS_SECTION_ID) {
      return graphMode;
    }

    return mostVisibleId;
  };

  const getVisibleSectionElement = (sectionId) => {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return null;
    }

    const escapedSectionId = typeof window.CSS?.escape === "function"
      ? window.CSS.escape(sectionId)
      : sectionId;

    const matches = Array.from(document.querySelectorAll(`#${escapedSectionId}`));
    if (matches.length === 0) {
      return null;
    }

    const visibleMatch = matches.find((element) => {
      const styles = window.getComputedStyle(element);
      return styles.display !== "none" && styles.visibility !== "hidden" && element.getClientRects().length > 0;
    });

    return visibleMatch || matches[0] || null;
  };

  const scrollToExploreSection = (sectionId) => {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return;
    }

    const targetId = SECTION_ID_MAP[sectionId] || sectionId;
    const target = getVisibleSectionElement(targetId);
    if (!target) {
      console.warn(`[Explore mobile nav] Missing section target: ${targetId}`);
      return;
    }

    target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleSectionSelect = (sectionId) => {
    if (GRAPH_SECTION_KEYS.has(sectionId) && graphMode !== sectionId) {
      setGraphMode(sectionId);
    }

    setActiveSection(sectionId);
    scrollToExploreSection(sectionId);
  };

  useEffect(() => {
    const nextActiveSection = resolveActiveSection();
    if (nextActiveSection) {
      setActiveSection(nextActiveSection);
    }
  }, [graphMode]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          visibleSectionRatiosRef.current[entry.target.id] = entry.isIntersecting ? entry.intersectionRatio : 0;
        });

        const nextActiveSection = resolveActiveSection();
        if (nextActiveSection) {
          setActiveSection(nextActiveSection);
        }
      },
      {
        root: null,
        rootMargin: "-18% 0px -52% 0px",
        threshold: [0.15, 0.3, 0.5, 0.7],
      }
    );

    ["explore-score", ANALYSIS_SECTION_ID, "explore-drivers", "explore-rarity", "explore-advanced"].forEach((sectionId) => {
      const element = getVisibleSectionElement(sectionId);
      if (element) {
        observer.observe(element);
      }
    });

    return () => observer.disconnect();
  }, [explorePayload, pageError, graphMode]);

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

  const handleTargetIdChange = (nextTargetId) => {
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

  const handleTargetChange = (event) => {
    const nextTargetId = String(event.target.value || "").trim();
    handleTargetIdChange(nextTargetId);
  };

  useEffect(() => {
    if (!heroSetPickerOpen || typeof document === "undefined") {
      return undefined;
    }

    const handleOutsideClick = (event) => {
      if (!event.target.closest?.('[data-hero-picker]')) {
        setHeroSetPickerOpen(false);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setHeroSetPickerOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("touchstart", handleOutsideClick, { passive: true });
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("touchstart", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [heroSetPickerOpen]);

  useEffect(() => {
    setHeroSetPickerOpen(false);
  }, [requestedTargetId]);

  const desktopSidebarContent = (
    <div className="space-y-5 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/72 p-4 backdrop-blur-sm">
      <div>
        <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Explore Controls
        </p>
        <div className="mt-3 space-y-3">
          <div>
            <label
              htmlFor="sidebar-rip-tcg"
              className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]"
            >
              TCG
            </label>
            <select
              id="sidebar-rip-tcg"
              disabled
              value="pokemon"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] opacity-80 outline-none"
            >
              <option value="pokemon">Pokemon</option>
            </select>
          </div>
          <div>
            <label
              htmlFor="sidebar-rip-target"
              className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]"
            >
              Set
            </label>
            <select
              id="sidebar-rip-target"
              value={requestedTargetId || ""}
              onChange={handleTargetChange}
              disabled={isPending || targets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {targets.map((target) => (
                <option key={`${target.target_type}:${target.target_id}`} value={target.target_id}>
                  {target.name}
                </option>
              ))}
            </select>
          </div>
          {selectedTarget?.era ? (
            <div className="flex items-center gap-2 px-1">
              <span className="text-xs font-medium text-[var(--text-secondary)]">Era</span>
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-0.5 text-xs text-[var(--text-secondary)]">
                {selectedTarget.era}
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="h-px w-full bg-[var(--border-subtle)]" />

      <div>
        <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Sections
        </p>
        <div className="mt-2">
          <SectionNavigation
            items={sectionNavItems}
            activeSection={activeSection}
            onSelect={handleSectionSelect}
          />
        </div>
      </div>
    </div>
  );

  const renderMobileToolsPanelContent = () => (
    <div className="space-y-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Explore Controls
        </p>
        <div className="mt-2 space-y-3">
          <div>
            <label htmlFor="mobile-rip-tcg" className="mb-1 block text-xs font-medium text-[var(--text-primary)]">
              TCG
            </label>
            <select
              id="mobile-rip-tcg"
              disabled
              value="pokemon"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] opacity-80 outline-none"
            >
              <option value="pokemon">Pokemon</option>
            </select>
          </div>
          <div>
            <label htmlFor="mobile-rip-target" className="mb-1 block text-xs font-medium text-[var(--text-primary)]">
              Set
            </label>
            <select
              id="mobile-rip-target"
              value={requestedTargetId || ""}
              onChange={handleTargetChange}
              disabled={isPending || targets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {targets.map((target) => (
                <option key={`${target.target_type}:${target.target_id}`} value={target.target_id}>
                  {target.name}
                </option>
              ))}
            </select>
          </div>
          {selectedTarget?.era ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--text-secondary)]">Era:</span>
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                {selectedTarget.era}
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );

  return (
    <main className="w-full overflow-x-hidden pb-8 pt-4 lg:py-8">
      <PublicProfileLocalScaffold
        profileBaseHref="/Explore/rip-statistics"
        mode="public"
        sectionItems={[]}
        mobileNavItems={[]}
        desktopSidebarContent={desktopSidebarContent}
        mobileToolsPanelContent={renderMobileToolsPanelContent}
        mobileToolsTitle="Explore Filters & Navigation"
        mobileToolsDescription="Switch TCG and set filters."
        mobileToolsPanelAriaLabel="Explore filters and navigation"
        mobileToolsTriggerLabel="Filters & Tools"
        mobileToolsTriggerTitle="Open filters and navigation"
        useFloatingToolsOnTablet
        forceCompactToolsBelow2xl
        centerContentIgnoringSidebar
        desktopContentOffsetClassName="xl:flex xl:justify-center"
        wrapDesktopContentInFrame={false}
        mobileBottomNavContent={() => (
          <CompactBottomSectionNav
            activeSection={activeSection}
            onSelect={handleSectionSelect}
          />
        )}
      >
        <div className="dashboard-container space-y-8 w-full max-w-full min-w-0 !p-0 !bg-transparent !border-0 !rounded-none xl:!p-6 xl:!bg-[rgba(255,255,255,0.02)] xl:!rounded-2xl xl:!border">
        {pageError ? (
          <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6">
            <p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p>
            <p className="mt-2 text-sm text-red-300">{pageError}</p>
          </section>
        ) : null}

        {!pageError && explorePayload ? (
          <>
            <section id="explore-score" className="page-hero-panel scroll-mt-24 rounded-xl px-4 py-6 md:rounded-2xl md:px-6 md:py-8 md:scroll-mt-28">
              <div className="mx-auto max-w-3xl text-center">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">RIP Statistics</p>
                <div ref={heroSetPickerRef} data-hero-picker className="relative mt-2 inline-flex max-w-full justify-center">
                  <button
                    type="button"
                    onClick={() => setHeroSetPickerOpen((open) => !open)}
                    disabled={isPending || targets.length === 0}
                    aria-expanded={heroSetPickerOpen}
                    aria-haspopup="listbox"
                    aria-controls="hero-set-picker-list"
                    className="inline-flex max-w-full items-center gap-2 rounded-lg px-2 py-1 text-3xl font-semibold text-[var(--text-primary)] transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] sm:text-4xl disabled:cursor-not-allowed disabled:opacity-90"
                    title={targets.length > 0 ? "Switch set" : "No sets available"}
                  >
                    <span className="truncate">{selectedName}</span>
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 20 20"
                      className={`h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform ${heroSetPickerOpen ? "rotate-180" : ""}`}
                      fill="currentColor"
                    >
                      <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                    </svg>
                  </button>

                  {heroSetPickerOpen ? (
                    <div
                      id="hero-set-picker-list"
                      role="listbox"
                      aria-label="Available sets"
                      className="absolute left-1/2 top-full z-30 mt-2 max-h-72 w-[min(36rem,92vw)] -translate-x-1/2 overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1.5 text-left shadow-[0_12px_30px_rgba(0,0,0,0.42)]"
                    >
                      {targets.map((target) => {
                        const isSelected = String(target.target_id) === String(requestedTargetId || "");
                        return (
                          <button
                            key={`hero-set-option:${target.target_type}:${target.target_id}`}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            onClick={() => {
                              handleTargetIdChange(String(target.target_id || ""));
                              setHeroSetPickerOpen(false);
                            }}
                            className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                              isSelected
                                ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                                : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                            }`}
                          >
                            <span className="truncate">{target.name}</span>
                            {isSelected ? (
                              <span className="ml-2 text-xs font-medium text-[var(--accent)]">Current</span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>

                <div className="mt-6 flex flex-col items-center gap-1.5">
                  <p className="text-[clamp(3rem,10vw,5rem)] font-semibold leading-tight text-[var(--text-primary)]">{displayedTopScore}</p>
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Pack Score</p>
                    <InfoPopover text={getFormattedTooltip("Pack Score")} />
                  </div>
                </div>

                <div className="mx-auto mt-4 w-full max-w-md">
                  <ScoreMeter score={topScoreRaw} rankTier={summary.pack_tier} />
                </div>

                <div className="mt-4 flex justify-center">
                  <RankBadge
                    rank={summary.pack_tier}
                    label="Pack Rank"
                    size="hero"
                    title={
                      summary.pack_rank === null || summary.pack_rank === undefined
                        ? "Pack Rank unavailable"
                        : `Pack rank #${summary.pack_rank}`
                    }
                  />
                </div>

                <InterpretationInsight
                  sectionMeta={packScoreMeta}
                  fallbackSummary={interpretation?.packScore}
                  showEvidence
                  maxEvidence={3}
                  evidenceLabel="Why this matters"
                  className="mx-auto mt-3 w-full max-w-2xl"
                />

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
              <div className="grid gap-4 xl:grid-cols-3">
                <ScorePillarCard
                  title="Profit"
                  score={displayedProfitScore}
                  rankValue={summary.profit_rank}
                  rankTier={summary.profit_tier}
                  rankLabel="Profit Rank"
                  sectionMeta={profitMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Profit")}
                  signals={[
                    { label: "Probability of Profit", value: formatPercent(summary.prob_profit, { probability: true }) },
                    { label: "EV / Mean Value", value: formatNumber(meanValueToCostRatio, 2) },
                    { label: "Median-to-Cost Ratio", value: formatNumber(medianValueToCostRatio, 2) },
                    { label: "P95-to-Cost Ratio", value: formatNumber(summary.p95_value_to_cost_ratio, 2) },
                  ]}
                  contextMetrics={[
                    { label: "Pack Cost", value: formatCurrency(summary.pack_cost) },
                    { label: "ROI", value: formatPercent(summary.roi_percent) },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={displayedSafetyScore}
                  rankValue={summary.safety_rank}
                  rankTier={summary.safety_tier}
                  rankLabel="Safety Rank"
                  sectionMeta={safetyMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Safety")}
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
                  sectionMeta={stabilityMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Stability")}
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

            <section id={ANALYSIS_SECTION_ID} className="scroll-mt-24 pt-7 md:scroll-mt-28">
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
                <div className="mb-1.5 w-full max-w-full overflow-hidden">
                  <div className="grid w-full grid-cols-3 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("outcome-distribution")}
                    aria-pressed={graphMode === "outcome-distribution"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "outcome-distribution"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">Outcome Distribution</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("historical-trend")}
                    aria-pressed={graphMode === "historical-trend"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "historical-trend"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">Historical Trend</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("pack-breakdown")}
                    aria-pressed={graphMode === "pack-breakdown"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "pack-breakdown"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">Pack Breakdown</span>
                  </button>
                  </div>
                </div>

                <InterpretationInsight
                  sectionMeta={graphSectionMeta}
                  fallbackSummary={graphSectionFallback}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />

                {graphMode === "pack-breakdown" && packBreakdownEvidenceRows.length > 0 ? (
                  <div className="mb-4 flex flex-wrap gap-2">
                    {packBreakdownEvidenceRows.map(([label, value]) => (
                      <span
                        key={`${label}:${value}`}
                        className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        <span className="text-[var(--text-secondary)]">{label}</span>
                        <span className="font-medium text-[var(--text-primary)]">{String(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}

                {graphMode === "historical-trend" ? (
                  <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} />
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

            <section className="pt-1">
              <div className="grid gap-4 xl:grid-cols-2 xl:items-start">
                <div id="explore-drivers" className="scroll-mt-24 md:scroll-mt-28">
                  <SectionCard title="Top Expected Value (EV) Drivers" subtitle="These cards contribute the most to expected pack value.">
                    <InterpretationInsight
                      sectionMeta={topEvDriversMeta}
                      fallbackSummary={interpretation?.topEvDrivers}
                      compact
                      showEvidence={false}
                      className="mb-3"
                    />

                    {topEvEvidenceRows.length > 0 ? (
                      <div className="mb-3 flex flex-wrap gap-2">
                        {topEvEvidenceRows.map(([label, value]) => (
                          <span
                            key={`${label}:${value}`}
                            className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                          >
                            <span>{label}</span>
                            <span className="font-medium text-[var(--text-primary)]">{String(value)}</span>
                          </span>
                        ))}
                      </div>
                    ) : null}

                    <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} />
                  </SectionCard>
                </div>

                <div className="space-y-4">
                  <div id="explore-rarity" className="scroll-mt-24 md:scroll-mt-28">
                    <SectionCard title="Rarity Pull Contribution" subtitle={null}>
                      <InterpretationInsight
                        sectionMeta={rarityContributionMeta}
                        fallbackSummary={interpretation?.rarityContribution}
                        compact
                        showEvidence
                        maxEvidence={4}
                        className="mb-3"
                      />
                      <RarityContributionContent rankings={rankings} />
                    </SectionCard>
                  </div>

                  <details id="explore-advanced" className="group scroll-mt-24 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-5 sm:p-6 md:scroll-mt-28">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-1 transition-colors hover:text-white">
                      <span className="text-lg font-semibold text-[var(--text-primary)]">Advanced Metrics</span>
                      <svg
                        aria-hidden="true"
                        viewBox="0 0 20 20"
                        className="h-5 w-5 flex-none text-[var(--text-secondary)] transition-transform duration-150"
                        fill="currentColor"
                      >
                        <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                      </svg>
                    </summary>
                    <style>{`
                      #explore-advanced svg {
                        transform: rotate(0deg);
                      }
                      #explore-advanced[open] svg {
                        transform: rotate(180deg);
                      }
                    `}</style>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">Deeper technical indicators for experienced users</p>

                    <InterpretationInsight
                      sectionMeta={advancedMetricsMeta}
                      fallbackSummary={interpretation?.advancedMetrics}
                      compact
                      showEvidence
                      maxEvidence={5}
                      className="mt-3"
                    />

                    <div className="mt-4 space-y-5">
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        <StatTile label="Expected Loss Per Pack" value={formatCurrency(summary.expected_loss_per_pack)} valueClassName="text-base" />
                        <StatTile label="Expected Loss When Losing" value={formatCurrency(summary.expected_loss_when_losing)} valueClassName="text-base" />
                        <StatTile label="Median Loss When Losing" value={formatCurrency(summary.median_loss_when_losing)} valueClassName="text-base" />
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        <StatTile label="Coefficient of Variation" value={formatNumber(summary.coefficient_of_variation, 2)} valueClassName="text-base" />
                        <StatTile label="P95 Value / Cost Ratio" value={formatNumber(summary.p95_value_to_cost_ratio, 2)} valueClassName="text-base" />
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        <StatTile label="HHI EV Concentration" value={formatNumber(summary.hhi_ev_concentration, 3)} valueClassName="text-base" />
                        <StatTile label="Effective Chase Count" value={formatNumber(summary.effective_chase_count, 2)} valueClassName="text-base" />
                      </div>
                    </div>
                  </details>
                </div>
              </div>
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
      </PublicProfileLocalScaffold>
    </main>
  );
}