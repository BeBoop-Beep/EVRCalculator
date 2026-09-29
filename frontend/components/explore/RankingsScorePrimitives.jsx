"use client";

import { RIP_SCORE_SCALE_BENCHMARK_10, RipScoreBadge } from "./RipScoreBadge";

const POSITION = {
  above: { glyph: "↑", word: "above" },
  below: { glyph: "↓", word: "below" },
  at: { glyph: "—", word: "at" },
};

export function BenchmarkPositionIndicator({ benchmarkPosition, deltaVsBenchmark, compact = false }) {
  const position = POSITION[benchmarkPosition] || POSITION.at;
  const delta = Number(deltaVsBenchmark);
  const amount = Number.isFinite(delta) ? Math.abs(delta).toFixed(1) : null;
  const aria = amount === null
    ? `${position.word} Pokémon Overall Average`
    : `${amount} points ${position.word} Pokémon Overall Average`;
  return <span data-benchmark-position={benchmarkPosition || "at"} aria-label={aria} title={aria} className="inline-flex items-center gap-1 text-[10px] font-semibold tabular-nums text-[var(--text-secondary)]">
    <span aria-hidden="true">{position.glyph}</span>{!compact && amount !== null ? <span aria-hidden="true">{benchmarkPosition === "above" ? "+" : benchmarkPosition === "below" ? "−" : ""}{amount}</span> : null}
  </span>;
}

export function RankingsRipScoreBadge({ metric, label = "RIP Score", compact = false }) {
  const rank = Number(metric?.rank), cohortSize = Number(metric?.cohortSize);
  const hasRank = Number.isFinite(rank) && Number.isFinite(cohortSize);
  return <span className="inline-flex flex-col items-center gap-1" data-rankings-rip-score data-rank={hasRank ? rank : undefined} data-cohort-size={hasRank ? cohortSize : undefined}>
    <RipScoreBadge score={metric?.score} tier={metric?.tier} compact={compact} label={label} scoreScale={RIP_SCORE_SCALE_BENCHMARK_10} />
    <BenchmarkPositionIndicator benchmarkPosition={metric?.benchmarkPosition} deltaVsBenchmark={metric?.deltaVsBenchmark} compact={compact} />
    {hasRank ? <span className="sr-only">Rank {rank} of {cohortSize}</span> : null}
  </span>;
}

export function BenchmarkReferenceRow({ reference = { label: "Pokémon Overall Average", score: 5, iconKey: "pokemon" } }) {
  return <div data-benchmark-reference className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]">
    <span aria-hidden="true" className="text-sm">◉</span><span>{reference.label}</span><strong className="tabular-nums text-[var(--text-primary)]">{Number(reference.score).toFixed(1)}</strong>
  </div>;
}
