export default function PortfolioSectionHeader({
  title = "Portfolio Intelligence",
  subtitle = "Track performance, holdings, and portfolio growth",
}) {
  return (
    <header className="space-y-1">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
      <p className="text-sm text-[var(--text-secondary)]">{subtitle}</p>
    </header>
  );
}