function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatScore(score) {
  const parsed = toOptionalNumber(score);
  return parsed === null ? null : Math.round(parsed).toString();
}

const PILLAR_ROWS = [
  ["Profit", "Profitability", "Profit profile", "Compares Expected Value, upside, and pack cost pressure."],
  ["Safety", "Safety", "Miss protection", "Shows how well the set protects against rough openings and downside outcomes."],
  ["Desirability", "Desirability", "Collector demand", "Reflects collector appeal and chase-card strength for this set."],
  ["Stability", "Stability", "Value spread", "Shows whether value is broadly distributed or concentrated in a few cards."],
];

export function selectDecisionSignals(input = {}) {
  const safeInput = input && typeof input === "object" ? input : {};
  const requestTimeout = safeInput.requestTimeout === true || safeInput.payload?.meta?.requestTimeout === true;
  const pillarSignals = Array.isArray(safeInput.pillarSignals) ? safeInput.pillarSignals : [];
  const signalByTitle = new Map(
    pillarSignals.filter(Boolean).map((signal) => [signal.title, signal])
  );
  const missingFields = [];
  const rows = PILLAR_ROWS.map(([title, label, fallbackSummary, detailSummary]) => {
    const signal = signalByTitle.get(title);
    if (!signal) {
      missingFields.push(title);
      return null;
    }
    return {
      label,
      scoreText: formatScore(signal.score),
      scoreTrend: signal.scoreTrend,
      rankTier: signal.rankTier,
      rankValue: signal.rankValue,
      summary: signal.highlight || fallbackSummary,
      detailSummary: signal.highlight || detailSummary,
    };
  }).filter(Boolean);

  return {
    rows,
    sourceUsed: "summary+pillarSignals",
    fallbackUsed: requestTimeout,
    diagnostics: {
      source: "summary+pillarSignals",
      status: requestTimeout && rows.length === 0 ? "loading" : rows.length > 0 ? "ready" : "unavailable",
      requestTimeout,
      missingFields: requestTimeout ? [] : missingFields,
      fallbackUsed: requestTimeout,
      warning:
        requestTimeout && rows.length === 0
          ? "Decision Signals loading: set page snapshot request timed out; retrying."
          : null,
    },
  };
}
