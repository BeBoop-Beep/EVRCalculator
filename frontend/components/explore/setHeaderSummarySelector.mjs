// Builds the stable "Set Header Summary Contract" used by the set-detail
// title/header card. Cards and Overview intentionally never load the full
// set /page payload, so the header must be able to render from whatever
// combination of explorePayload / shellPayload / market dashboard data /
// already-loaded client state happens to be available for the active set —
// never from "whatever the active tab happens to have fetched."
//
// Field-by-field fallback priority (matches the product spec):
//   1. fresh full explorePayload, when available and matching the active set
//   2. shellPayload
//   3. marketDashboardPayload / marketDashboardState (set value + history only)
//   4. already-loaded same-set client state (previousSameSetSummary)
//   5. safe fallback placeholders (null values; callers render "Coming soon"/"—")

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalString(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function pickNumber(...values) {
  for (const value of values) {
    const parsed = toOptionalNumber(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function pickString(...values) {
  for (const value of values) {
    const parsed = toOptionalString(value);
    if (parsed) return parsed;
  }
  return null;
}

function mergeDefined(...sources) {
  const result = {};
  sources.forEach((source) => {
    Object.entries(asObject(source)).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        result[key] = value;
      }
    });
  });
  return result;
}

function normalizeSetIdentity(raw) {
  const set = asObject(raw?.set || raw?.setIdentity || raw?.set_identity);
  return {
    id: toOptionalString(set.id ?? set.set_id),
    name: toOptionalString(set.name ?? set.set_name),
    slug: toOptionalString(set.slug ?? set.canonical_key),
    logoImageUrl: toOptionalString(set.logo_image_url ?? set.logoImageUrl),
    symbolImageUrl: toOptionalString(set.symbol_image_url ?? set.symbolImageUrl),
    heroImageUrl: toOptionalString(set.hero_image_url ?? set.heroImageUrl),
  };
}

function normalizeTargetIdentity(target) {
  const safeTarget = asObject(target);
  return {
    id: toOptionalString(safeTarget.id ?? safeTarget.set_id ?? safeTarget.target_id),
    name: toOptionalString(safeTarget.name ?? safeTarget.set_name),
    slug: toOptionalString(safeTarget.slug ?? safeTarget.canonical_key),
    logoImageUrl: toOptionalString(safeTarget.logo_image_url),
    symbolImageUrl: toOptionalString(safeTarget.symbol_image_url),
    heroImageUrl: toOptionalString(safeTarget.hero_image_url),
  };
}

function getAverageLoss(summarySource) {
  const meanValue = toOptionalNumber(summarySource?.mean_value);
  const packCost = toOptionalNumber(summarySource?.pack_cost);
  if (meanValue !== null && packCost !== null) {
    return Math.min(meanValue - packCost, 0);
  }
  const expectedLossPerPack = toOptionalNumber(summarySource?.expected_loss_per_pack);
  return expectedLossPerPack === null ? null : -Math.abs(expectedLossPerPack);
}

function getSparklinePoints({ contractStandard, marketDashboardState, marketDashboardPayload, previousSetValue }) {
  if (Array.isArray(contractStandard?.history) && contractStandard.history.length > 0) {
    return contractStandard.history;
  }
  const stateHistory = marketDashboardState?.setValue?.history;
  if (Array.isArray(stateHistory) && stateHistory.length > 0) {
    return stateHistory;
  }
  const rawHistory =
    marketDashboardPayload?.setValueHistoriesByScope?.standard ||
    marketDashboardPayload?.set_value_histories_by_scope?.standard;
  if (Array.isArray(rawHistory) && rawHistory.length > 0) {
    return rawHistory;
  }
  return Array.isArray(previousSetValue?.sparklinePoints) ? previousSetValue.sparklinePoints : [];
}

export function buildSetHeaderSummary({
  explorePayload = null,
  shellPayload = null,
  marketDashboardPayload = null,
  marketDashboardState = null,
  setValueContract = null,
  selectedTarget = null,
  resolvedSetResourceId = null,
  explorePayloadIsFresh = false,
  // A set switch can leave the shellPayload prop holding the PREVIOUS set's
  // data for a render or two before the new set's shell commits. Using that
  // mismatched shell would render the previous set's metrics under the new
  // set's title. Callers pass false when the shell's identity does not match
  // the active set; the shell is then ignored for summary/interpretation/
  // identity (the metrics fall through to the same-set cache or null, and the
  // caller renders a pending state rather than leaking the wrong set).
  shellPayloadIsForActiveSet = true,
  previousSameSetSummary = null,
} = {}) {
  const resolvedSetId = toOptionalString(resolvedSetResourceId);
  const previousForSet =
    previousSameSetSummary && previousSameSetSummary.setId && previousSameSetSummary.setId === resolvedSetId
      ? previousSameSetSummary
      : null;

  const effectiveShellPayload = shellPayloadIsForActiveSet === false ? null : shellPayload;

  const exploreSummary = explorePayloadIsFresh ? asObject(explorePayload?.summary) : {};
  const shellSummary = asObject(effectiveShellPayload?.summary);
  const previousSummary = asObject(previousForSet?.raw?.summary);
  const summarySource = { ...previousSummary, ...shellSummary, ...exploreSummary };

  const exploreInterpretation = explorePayloadIsFresh ? explorePayload?.interpretation : null;
  const shellInterpretation = effectiveShellPayload?.interpretation;
  const previousInterpretation = previousForSet?.raw?.interpretation;
  const interpretation = exploreInterpretation || shellInterpretation || previousInterpretation || null;
  const packScoreMeta = interpretation?.meta?.packScore || null;

  const exploreIdentity = explorePayloadIsFresh ? normalizeSetIdentity(explorePayload) : {};
  const shellIdentity = normalizeSetIdentity(effectiveShellPayload);
  const targetIdentity = normalizeTargetIdentity(selectedTarget);
  const previousIdentity = asObject(previousForSet?.set);

  const set = {
    id:
      pickString(exploreIdentity.id, shellIdentity.id, targetIdentity.id, previousIdentity.id, resolvedSetId) ||
      null,
    name: pickString(exploreIdentity.name, shellIdentity.name, targetIdentity.name, previousIdentity.name),
    slug: pickString(exploreIdentity.slug, shellIdentity.slug, targetIdentity.slug, previousIdentity.slug),
    logoImageUrl: pickString(
      exploreIdentity.logoImageUrl,
      shellIdentity.logoImageUrl,
      targetIdentity.logoImageUrl,
      previousIdentity.logoImageUrl
    ),
    symbolImageUrl: pickString(
      exploreIdentity.symbolImageUrl,
      shellIdentity.symbolImageUrl,
      targetIdentity.symbolImageUrl,
      previousIdentity.symbolImageUrl
    ),
    heroImageUrl: pickString(
      exploreIdentity.heroImageUrl,
      shellIdentity.heroImageUrl,
      targetIdentity.heroImageUrl,
      previousIdentity.heroImageUrl
    ),
  };

  const score = pickNumber(summarySource.relative_pack_score, summarySource.pack_score);
  const rank = pickNumber(summarySource.pack_rank);
  const tier = pickString(summarySource.pack_tier);

  const recommendationBadge = pickString(packScoreMeta?.label, previousForSet?.recommendationBadge);
  const recommendationSummary = pickString(
    packScoreMeta?.summary,
    interpretation?.packScore,
    previousForSet?.recommendationSummary
  );

  const packCost = pickNumber(summarySource.pack_cost);
  const expectedValue = pickNumber(summarySource.mean_value);
  const averageHitValue = pickNumber(summarySource.average_hit_value);
  const averageLoss = pickNumber(getAverageLoss(summarySource), previousForSet?.averageLoss);
  const chanceToBeatPackCost = pickNumber(summarySource.prob_profit);
  const chanceAtBigPull = pickNumber(summarySource.prob_big_hit);

  // Set value already has a dedicated, well-tested blended contract
  // (buildSetValueContract) that layers direct fetch state, market dashboard
  // data, and shell/explore fallbacks — reuse it as the primary source and
  // only reach for the raw market dashboard payload/state or the sticky
  // same-set cache when the contract itself has nothing yet.
  const contractStandard = setValueContract?.scopes?.standard || null;
  const previousSetValue = previousForSet?.setValue || null;
  const sparklinePoints = getSparklinePoints({
    contractStandard,
    marketDashboardState,
    marketDashboardPayload,
    previousSetValue,
  });
  const contractCurrentValue = toOptionalNumber(contractStandard?.currentValue ?? setValueContract?.current?.value);
  const setValueCurrent = pickNumber(
    contractCurrentValue,
    sparklinePoints.at(-1)?.setValue ?? sparklinePoints.at(-1)?.value,
    previousSetValue?.current
  );
  const setValueDelta30dAmount = pickNumber(contractStandard?.delta30dAmount, previousSetValue?.delta30dAmount);
  const setValueDelta30dPercent = pickNumber(contractStandard?.delta30dPercent, previousSetValue?.delta30dPercent);
  const setValueAsOf = pickString(contractStandard?.asOf, setValueContract?.current?.asOf, previousSetValue?.asOf);

  const missingFields = [];
  if (score === null) missingFields.push("score");
  if (recommendationBadge === null) missingFields.push("recommendationBadge");
  if (recommendationSummary === null) missingFields.push("recommendationSummary");
  if (averageHitValue === null) missingFields.push("averageHitValue");
  if (setValueCurrent === null) missingFields.push("setValue.current");

  return {
    setId: set.id,
    set,
    score,
    rank,
    tier,
    recommendationBadge,
    recommendationSummary,
    packCost,
    expectedValue,
    averageHitValue,
    averageLoss,
    chanceToBeatPackCost,
    chanceAtBigPull,
    setValue: {
      current: setValueCurrent,
      delta30dAmount: setValueDelta30dAmount,
      delta30dPercent: setValueDelta30dPercent,
      sparklinePoints,
      asOf: setValueAsOf,
    },
    diagnostics: {
      source: "set_header_summary",
      explorePayloadIsFresh: Boolean(explorePayloadIsFresh),
      usedShellPayload: Boolean(effectiveShellPayload),
      shellPayloadIgnoredIdentityMismatch: Boolean(shellPayload) && shellPayloadIsForActiveSet === false,
      usedPreviousSameSetSummary: Boolean(previousForSet),
      missingFields,
    },
    // Cache-friendly raw snapshot for the next render's previousSameSetSummary.
    raw: {
      summary: mergeDefined(previousSummary, shellSummary, exploreSummary),
      interpretation,
    },
  };
}
