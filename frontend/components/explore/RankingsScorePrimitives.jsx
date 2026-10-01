"use client";

import { RIP_SCORE_SCALE_BENCHMARK_10, RipScoreBadge } from "./RipScoreBadge";
export function RankingsRipScoreBadge({ metric, label = "RIP Score", compact = false }) {
  const rank = Number(metric?.rank), cohortSize = Number(metric?.cohortSize);
  const hasRank = Number.isFinite(rank) && Number.isFinite(cohortSize);
  return <span className="inline-flex flex-col items-center gap-1" data-rankings-rip-score data-rank={hasRank ? rank : undefined} data-cohort-size={hasRank ? cohortSize : undefined}>
    <RipScoreBadge score={metric?.score} tier={metric?.tier} compact={compact} label={label} showLabel={false} scoreScale={RIP_SCORE_SCALE_BENCHMARK_10} accentColor="rgba(192,132,252,0.96)" />
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

export function BenchmarkReferenceRow({ reference = { label: "Pokémon Overall Average", score: 5, iconKey: "pokemon" } }) {
  return <div data-benchmark-reference className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]">
    <span aria-hidden="true" className="text-sm">◉</span><span>{reference.label}</span><strong className="tabular-nums text-[var(--text-primary)]">{Number(reference.score).toFixed(1)}</strong>
  </div>;
}
