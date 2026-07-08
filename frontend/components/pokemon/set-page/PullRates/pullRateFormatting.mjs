// Pure formatting/shaping helpers for pull-rate assumption rows. Extracted
// from PullRateAssumptionsCard.jsx (sibling in this folder) so the new
// section-level components (HitRateSummarySection, PullRateTableSection,
// AdvancedOddsSection) can derive summaries from the same data without
// duplicating the formatting logic.

export function toFiniteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatOddsDenominator(denominator) {
  const parsed = toFiniteNumber(denominator);
  if (parsed === null || parsed <= 0) {
    return "—";
  }

  let formatted;
  if (parsed >= 10) {
    formatted = Math.round(parsed).toLocaleString("en-US");
  } else if (Number.isInteger(parsed)) {
    formatted = String(parsed);
  } else {
    formatted = parsed.toFixed(1);
  }

  return `1 in ${formatted} packs`;
}

export function formatCardCount(count) {
  const parsed = toFiniteNumber(count);
  if (parsed === null || parsed <= 0) {
    return "—";
  }
  return String(Math.round(parsed));
}

export function formatRarityLabel(rarity) {
  const label = String(rarity || "").trim();
  if (!label) {
    return "Unknown";
  }

  return label
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatGroupLabel(groupValue) {
  const key = String(groupValue || "").trim().toLowerCase();
  if (!key) {
    return "Pull Rate Assumptions";
  }
  if (key === "pack_structure") {
    return "Pack Structure";
  }
  if (key === "hit_rarity_model") {
    return "Hit Rarity Model";
  }
  if (key === "special_pack_rules") {
    return "Special Pack Rules";
  }
  return key
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatPerPackValue(value) {
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(2);
}

export function formatPullFrequency(row, groupKey) {
  const expected = toFiniteNumber(row?.expectedCardsPerPack ?? row?.expected_cards_per_pack);
  const rarityOddsDenominator = toFiniteNumber(row?.rarityOddsDenominator ?? row?.rarity_odds_denominator);
  const normalizedGroup = String(row?.group || groupKey || "").trim().toLowerCase();

  const formatFromExpected = () => {
    if (expected === null || expected <= 0) {
      return "—";
    }
    if (expected >= 1) {
      return `${formatPerPackValue(expected)} per pack`;
    }
    return formatOddsDenominator(1 / expected);
  };

  if (normalizedGroup === "pack_structure") {
    return formatFromExpected();
  }

  if (normalizedGroup === "hit_rarity_model" || normalizedGroup === "special_pack_rules") {
    if (rarityOddsDenominator && rarityOddsDenominator > 0) {
      return formatOddsDenominator(rarityOddsDenominator);
    }
    return formatFromExpected();
  }

  if (rarityOddsDenominator && rarityOddsDenominator > 0) {
    return formatOddsDenominator(rarityOddsDenominator);
  }
  return formatFromExpected();
}

export function buildGroupsForRender(pullRateAssumptions) {
  const sourceGroups = Array.isArray(pullRateAssumptions?.groups) ? pullRateAssumptions.groups : [];
  const groups = sourceGroups
    .map((group) => ({
      key: group?.key || null,
      label: group?.label || formatGroupLabel(group?.key),
      rows: Array.isArray(group?.rows) ? group.rows : [],
    }))
    .filter((group) => group.rows.length > 0);

  if (groups.length > 0) {
    return groups;
  }

  const rows = Array.isArray(pullRateAssumptions?.rows) ? pullRateAssumptions.rows : [];
  if (rows.length === 0) {
    return [];
  }

  return [
    {
      key: "flat_model",
      label: "Pull Rate Assumptions",
      rows,
    },
  ];
}
