function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstArray(payload, paths) {
  for (const path of paths) {
    const value = path.reduce((current, key) => current?.[key], payload);
    if (Array.isArray(value)) {
      return { rows: value, source: path.join(".") };
    }
  }
  return { rows: [], source: null };
}

function freshnessFor(payload, sectionKey) {
  const freshness = payload?.meta?.sectionFreshness?.[sectionKey];
  return freshness && typeof freshness === "object" ? freshness : null;
}

function isRequestTimeoutFallback(payload) {
  const meta = payload?.meta || {};
  if (meta.requestTimeout === true || meta.fallbackReason === "request_timeout") {
    return true;
  }
  const errors = Array.isArray(meta.errors) ? meta.errors : [];
  return errors.some((error) => String(error?.code || "").includes("TIMEOUT"));
}

export function selectSimulationDrivers(payload = {}) {
  const { rows: rawRows, source } = firstArray(payload, [
    ["top_hits"],
    ["topHits"],
    ["interpretation", "topEvDrivers", "rows"],
    ["interpretation", "top_ev_drivers", "rows"],
    ["rip_statistics", "top_hits"],
    ["ripStatistics", "topHits"],
  ]);
  const rows = asArray(rawRows)
    .map((row) => ({
      ...row,
      card_name: row?.card_name ?? row?.cardName ?? row?.name,
      ev_contribution: toOptionalNumber(row?.ev_contribution ?? row?.evContribution ?? row?.contribution),
      current_near_mint_price: toOptionalNumber(
        row?.current_near_mint_price ??
          row?.currentNearMintPrice ??
          row?.price_used ??
          row?.priceUsed ??
          row?.market_price ??
          row?.marketPrice
      ),
      image_url: row?.image_url ?? row?.imageUrl,
      image_small_url: row?.image_small_url ?? row?.imageSmallUrl,
      image_large_url: row?.image_large_url ?? row?.imageLargeUrl,
    }))
    .filter((row) => row.card_name || row.ev_contribution !== null);

  const sources = payload?.meta?.sources || {};
  const warnings = asArray(payload?.meta?.warnings);
  const freshness = freshnessFor(payload, "simulationDrivers");
  const requestTimeout = isRequestTimeoutFallback(payload);
  const fallbackUsed =
    sources.explore_rip_statistics_latest &&
    sources.explore_rip_statistics_latest !== "OK" &&
    sources.simulation_latest_by_target === "OK";
  const backendSourceFailure =
    sources.simulation_input_cards === "FAILED"
      ? "simulation_input_cards"
      : sources.simulation_input_cards === "NO_ROWS"
      ? "simulation_input_cards"
      : null;
  const missingBackendSource = rows.length === 0 && !requestTimeout ? backendSourceFailure : null;

  return {
    rows,
    sourceUsed: source,
    fallbackUsed: Boolean(fallbackUsed),
    diagnostics: {
      source,
      rowCount: rows.length,
      freshness,
      freshnessStatus: freshness?.status || null,
      status: requestTimeout && rows.length === 0 ? "loading" : rows.length > 0 ? "ready" : "unavailable",
      requestTimeout,
      dataAsOf: freshness?.dataAsOf || null,
      lastSuccessfulAt: freshness?.lastSuccessfulAt || null,
      attemptedAt: freshness?.attemptedAt || null,
      missingFields: rows.length === 0 && !requestTimeout ? ["top_hits"] : [],
      sources,
      fallbackUsed: Boolean(fallbackUsed),
      missingBackendSource,
      warning:
        requestTimeout && rows.length === 0
          ? "Simulation Drivers loading: set page snapshot request timed out; retrying."
          : rows.length === 0
          ? missingBackendSource
            ? `Simulation Drivers unavailable: backend source ${missingBackendSource} is ${sources[missingBackendSource]}.`
            : warnings.find((warning) => String(warning).toLowerCase().includes("top hits")) ||
              "Simulation Drivers unavailable: no top_hits rows were returned in the current payload."
          : null,
    },
  };
}
