"use client";

import { RIP_SCORE_SCALE_BENCHMARK_10, RipScoreBadge } from "./RipScoreBadge";
import { getTierTone } from "@/lib/explore/interpretationTone";
export function RankingsRipScoreBadge({ metric, label = "RIP Score", compact = false }) {
  const rank = Number(metric?.rank), cohortSize = Number(metric?.cohortSize);
  const hasRank = Number.isFinite(rank) && Number.isFinite(cohortSize);
  return <span className="inline-flex flex-col items-center gap-1" data-rankings-rip-score data-rank={hasRank ? rank : undefined} data-cohort-size={hasRank ? cohortSize : undefined}>
    <RipScoreBadge score={metric?.score} tier={metric?.tier} compact={compact} label={label} showLabel={false} scoreScale={RIP_SCORE_SCALE_BENCHMARK_10} />
    {hasRank ? <span className="sr-only">Rank {rank} of {cohortSize}</span> : null}
  </span>;
}

export function RankingsCompactScore({ metric, label }) {
  return <RankingsNeutralMetric metric={metric} label={label} />;
}

export function RankingsNeutralMetric({ metric, label }) {
  const score = Number(metric?.score);
  return <span data-rankings-neutral-metric aria-label={`${label}: ${Number.isFinite(score) ? score.toFixed(1) : "Unavailable"}`} className="font-semibold tabular-nums text-[var(--text-primary)]">
    {Number.isFinite(score) ? score.toFixed(1) : "—"}
  </span>;
}

// Benchmark Set/Era component score (Financial / Collector Appeal / Chase): a
// compact number with a thin border in the metric's OWN tier colour.  No
// caption, no direction arrow, no card chrome.  Not for absolute Product/Card
// score cells.
export function RankingsBenchmarkComponentScore({ metric, label }) {
  const score = Number(metric?.score);
  const available = metric?.score !== null && metric?.score !== undefined && Number.isFinite(score);
  const tone = metric?.tier ? getTierTone(metric.tier) : null;
  return <span data-rankings-benchmark-component-score data-tier={metric?.tier || undefined} role="img" aria-label={`${label}: ${available ? score.toFixed(1) : "Unavailable"}`} className="inline-flex min-w-[2.75rem] items-center justify-center rounded-md border px-2 py-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]" style={{ borderColor: tone?.accentColor || "var(--border-subtle)", borderWidth: "1px" }}>
    <span aria-hidden="true">{available ? score.toFixed(1) : "—"}</span>
  </span>;
}

export function BenchmarkReferenceRow({ reference = { label: "Pokémon Overall Average", score: 5, iconKey: "pokemon" } }) {
  return <div data-benchmark-reference className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]">
    <span aria-hidden="true" className="text-sm">◉</span><span>{reference.label}</span><strong className="tabular-nums text-[var(--text-primary)]">{Number(reference.score).toFixed(1)}</strong>
  </div>;
}
