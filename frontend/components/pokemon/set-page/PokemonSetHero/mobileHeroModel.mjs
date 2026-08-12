// Presentation-only view model for the mobile/tablet set hero. Every number
// arrives already computed by the page — this module chooses text and
// availability, never values.

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cleanText(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function formatTier(tier) {
  const text = cleanText(tier);
  if (!text) return null;
  return /\btier$/i.test(text) ? text : `${text} Tier`;
}

export function selectMobileHeroModel(input = {}) {
  const setValue = input?.setValue || {};
  const rip = input?.rip || {};

  const current = toFiniteNumber(setValue.current);
  const deltaAmount = toFiniteNumber(setValue.deltaAmount);
  const deltaPercent = toFiniteNumber(setValue.deltaPercent);
  const windowLabel = cleanText(setValue.windowLabel);

  const direction =
    deltaAmount === null
      ? "neutral"
      : deltaAmount < 0
      ? "negative"
      : deltaAmount > 0
      ? "positive"
      : "neutral";

  // Magnitude only. The caller pairs this with a direction glyph and an
  // accessible label so movement is never conveyed by colour alone.
  const deltaText =
    deltaAmount === null && deltaPercent === null
      ? null
      : [
          deltaAmount === null ? null : currencyFormatter.format(Math.abs(deltaAmount)),
          deltaPercent === null ? null : `${Math.abs(deltaPercent).toFixed(1)}%`,
          windowLabel,
        ]
          .filter(Boolean)
          .join(" · ");

  const score = toFiniteNumber(rip.score);
  const tierText = formatTier(rip.tier);
  const rank = toFiniteNumber(rip.rank);
  // No `verdict`. It carried the retired interpretation engine's label, which
  // describes neither Financial RIP V3 nor Collector Appeal V3.
  const hasRip = score !== null || tierText !== null || rank !== null;

  return {
    identity: {
      name: cleanText(input.setName) || "Selected Set",
      era: cleanText(input.era),
      logoUrl: cleanText(input.logoUrl),
      hasLogo: cleanText(input.logoUrl) !== null,
    },
    value: {
      hasValue: current !== null,
      amountText: current === null ? "—" : currencyFormatter.format(current),
      deltaText,
      direction,
    },
    rip: {
      label: cleanText(rip.label) || "Overall RIP",
      hasRip,
      scoreText: score === null ? null : String(Math.round(score)),
      tierText,
      rankText: rank === null ? null : `Rank #${Math.round(rank)}`,
      cohortSize: toFiniteNumber(rip.cohortSize),
      // Only offer a tap target when there is something to navigate to.
      isActionable: hasRip,
    },
  };
}
