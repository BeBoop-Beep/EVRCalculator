import { benchmarkPosition, formatBenchmarkScore } from "./ripBenchmarkPresentation.mjs";

export default function BenchmarkScoreBadge({ metric, label = "RIP Score", compact = false }) {
  const score = metric?.available ? metric.score : null;
  const position = benchmarkPosition(score);
  const rank = metric?.rank && metric?.cohortSize ? `, rank ${metric.rank} of ${metric.cohortSize}` : "";
  const aria = score === null ? `${label} unavailable` : `${label} ${Number(score).toFixed(1)} out of 10, ${position.toLowerCase()}${rank}`;
  return <div className={compact ? "text-right" : ""} aria-label={aria} data-benchmark-score>
    <strong className={`${compact ? "text-sm" : "text-base"} tabular-nums text-[var(--text-primary)]`}>{formatBenchmarkScore(score)}</strong>
    {score !== null ? <span className="block text-[10px] leading-tight text-[var(--text-secondary)]">{position}</span> : null}
    {metric?.rank && metric?.cohortSize ? <span className="block text-[10px] text-[var(--text-secondary)]">#{metric.rank} of {metric.cohortSize}</span> : null}
  </div>;
}
