function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function objectOrEmpty(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function selectFinancialRankDrivers(rows = []) {
  const ranked = (Array.isArray(rows) ? rows : [])
    .filter((row) => numberOrNull(row?.rankValue) !== null && numberOrNull(row?.cohortSize) !== null)
    .map((row) => ({
      key: row.key,
      title: row.title,
      rank: numberOrNull(row.rankValue),
      cohortSize: numberOrNull(row.cohortSize),
      tier: row.rankTier ?? null,
    }))
    .sort((a, b) => a.rank - b.rank);

  if (ranked.length < 3) return { strengths: [], drags: [], available: false };
  return {
    strengths: ranked.slice(0, 2),
    drags: ranked.slice(-1),
    available: true,
  };
}

export function selectCollectorRankDrivers(rows = []) {
  const ranked = (Array.isArray(rows) ? rows : [])
    .filter((row) => numberOrNull(row?.rank) !== null && numberOrNull(row?.cohortSize) !== null)
    .map((row) => ({ key: row.key, title: row.title, rank: numberOrNull(row.rank), cohortSize: numberOrNull(row.cohortSize), tier: row.tier ?? null }));
  if (ranked.length !== 2) return { strengths: [], drags: [], available: false };
  const sorted = [...ranked].sort((a, b) => a.rank - b.rank);
  const topHalf = (item) => item.rank <= Math.ceil(item.cohortSize / 2);
  if (sorted.every(topHalf)) return { strengths: sorted, drags: [], available: true };
  if (sorted.every((item) => !topHalf(item))) return { strengths: [], drags: sorted.reverse(), available: true };
  return { strengths: [sorted[0]], drags: [sorted[1]], available: true };
}

function selectSubjectPath(value) {
  const path = objectOrEmpty(value);
  const name = path.cardName ?? path.card_name ?? null;
  const id = path.canonicalCardId ?? path.canonical_card_id ?? null;
  if (!name && !id) return null;
  const odds = numberOrNull(path.impliedOdds ?? path.implied_odds);
  return {
    canonicalCardId: id,
    cardName: name,
    cardNumber: path.cardNumber ?? path.card_number ?? null,
    rarity: path.rarity ?? null,
    currentMarketPrice: numberOrNull(path.currentMarketPrice ?? path.current_market_price ?? path.marketPrice ?? path.market_price),
    imageUrl: path.imageUrl ?? path.image_url ?? null,
    modeledProbability: numberOrNull(path.modeledProbability ?? path.modeled_probability),
    impliedOdds: odds !== null && odds > 0 ? odds : null,
  };
}

export function selectCollectorDriverSubjects(canonical = {}) {
  const appeal = objectOrEmpty(canonical.collectorAppeal);
  return (Array.isArray(appeal.topSubjects) ? appeal.topSubjects : [])
    .map((value) => {
      const subject = objectOrEmpty(value);
      const accessiblePath = selectSubjectPath(subject.accessiblePath ?? subject.accessible_path);
      const elitePath = selectSubjectPath(subject.elitePath ?? subject.elite_path);
      if (!subject.subjectName || (!accessiblePath && !elitePath)) return null;
      const demandShare = numberOrNull(subject.demandShare ?? subject.demand_share);
      return {
        subjectName: subject.subjectName,
        demandShare,
        demandShareLabel: demandShare === null ? null : demandShare > 0 && demandShare < 0.01 ? "<1%" : `${Math.round(demandShare * 100)}%`,
        cardCount: numberOrNull(subject.cardCount),
        bestRarityBucket: subject.bestRarityBucket ?? null,
        accessiblePath,
        elitePath,
      };
    })
    .filter(Boolean)
    .slice(0, 3);
}

export function selectCollectorDiagnostic(canonical = {}) {
  const diagnostic = objectOrEmpty(objectOrEmpty(canonical.collectorAppeal).diagnostics).dualPathDepth;
  const safe = objectOrEmpty(diagnostic);
  const rawValue = numberOrNull(safe.rawValue);
  return {
    available: rawValue !== null,
    rawValue,
    displayPercent: numberOrNull(safe.displayPercent),
    subjectsWithMultiplePaths: numberOrNull(safe.subjectsWithMultiplePaths),
    note: safe.note ?? "Not part of the current Collector Appeal score.",
  };
}
