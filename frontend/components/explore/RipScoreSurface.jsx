import { getRipTierPresentation } from "./ripTierPresentation.mjs";

export default function RipScoreSurface({ tier, prominent = false, metricKey, className = "", children }) {
  const presentation = getRipTierPresentation(tier, { strength: prominent ? "hero" : "supporting" });
  return (
    <div
      data-rip-score={metricKey}
      data-score-tier={presentation.tier || "unavailable"}
      data-score-surface={prominent ? "primary" : "supporting"}
      style={presentation.style}
      className={`relative flex min-w-0 w-full overflow-hidden flex-col rounded-[.875rem] border border-[var(--tier-border)] bg-[linear-gradient(128deg,var(--tier-surface),rgba(2,8,23,.76)_68%)] shadow-[inset_0_1px_0_color-mix(in_srgb,var(--tier-color)_12%,rgba(255,255,255,.04))] ${prominent ? "bg-[linear-gradient(115deg,var(--tier-surface),rgba(2,8,23,.84)_72%)] shadow-[inset_0_1px_0_color-mix(in_srgb,var(--tier-color)_22%,rgba(255,255,255,.04)),0_12px_32px_rgba(0,0,0,.14)]" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
