function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatScore(score) {
  const parsed = toOptionalNumber(score);
  return parsed === null ? null : Math.round(parsed).toString();
}

// Label deliberately matches the Insights RIP Score Breakdown pillar name
// ("Profit") so the same pillar never reads as two different signals.
const PILLAR_ROWS = [
  ["Profit", "Profit", "Profit profile", "Compares Expected Value, upside, and pack cost pressure."],
  ["Safety", "Safety", "Miss protection", "Shows how well the set protects against rough openings and downside outcomes."],
  ["Stability", "Stability", "Value spread", "Shows whether value is broadly distributed or concentrated in a few cards."],
];

function normalizeTitle(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ");
}

export function selectDecisionSignals(input = {}) {
  const safeInput = input && typeof input === "object" ? input : {};
  const requestTimeout = safeInput.requestTimeout === true || safeInput.payload?.meta?.requestTimeout === true;
  const pillarSignals = Array.isArray(safeInput.pillarSignals) ? safeInput.pillarSignals : [];
  const trackedRows = Array.isArray(safeInput.trackedRows) ? safeInput.trackedRows : [];
  const signalByTitle = new Map(
    pillarSignals
      .filter(Boolean)
      .map((signal) => [normalizeTitle(signal.title), signal])
      .filter(([title]) => Boolean(title))
  );
  const missingFields = [];
  const rows = PILLAR_ROWS.map(([title, label, fallbackSummary, detailSummary]) => {
    const signal = signalByTitle.get(normalizeTitle(title));
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
  })
    .filter(Boolean)
    .concat(
      trackedRows
        .map((row) => ({
          label: row?.label || null,
          scoreText: row?.scoreText || null,
          scoreTrend: row?.scoreTrend || null,
          rankTier: row?.rankTier || null,
          rankValue: toOptionalNumber(row?.rankValue),
          summary: row?.summary || null,
          detailSummary: row?.detailSummary || row?.summary || null,
        }))
        .filter((row) => row.label)
    );

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
