import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

export default function MiniMarketSparkline({ points = [], color = "var(--text-secondary)" }) {
  const valid = points.filter((point) => Number.isFinite(point?.value));
  if (valid.length < 2) return <span data-mini-market-sparkline-empty aria-hidden="true" className="block w-[4.25rem] text-center text-xs text-[var(--text-secondary)]">—</span>;
  const [min, max] = buildMarketSparklineDomain(valid, { valueKey: "value" });
  const range = max - min || 1;
  const coordinates = valid.map((point, index) => {
    const x = (index / (valid.length - 1)) * 68;
    const y = 26 - ((point.value - min) / range) * 24;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <svg data-mini-market-sparkline data-point-count={valid.length} aria-hidden="true" viewBox="0 0 68 28" preserveAspectRatio="none" className="h-7 w-[4.25rem] overflow-visible">
      <polyline points={coordinates} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
