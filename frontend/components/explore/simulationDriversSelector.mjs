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
  const fallbackUsed =
    sources.explore_rip_statistics_latest &&
    sources.explore_rip_statistics_latest !== "OK" &&
    sources.simulation_latest_by_target === "OK";
  const missingBackendSource =
    sources.simulation_input_cards === "FAILED"
      ? "simulation_input_cards"
      : sources.simulation_input_cards === "NO_ROWS"
      ? "simulation_input_cards"
      : null;

  return {
    rows,
    sourceUsed: source,
    fallbackUsed: Boolean(fallbackUsed),
    diagnostics: {
      source,
      rowCount: rows.length,
      missingFields: rows.length === 0 ? ["top_hits"] : [],
      sources,
      fallbackUsed: Boolean(fallbackUsed),
      missingBackendSource,
      warning:
        rows.length === 0
          ? missingBackendSource
            ? `Simulation Drivers unavailable: backend source ${missingBackendSource} is ${sources[missingBackendSource]}.`
            : warnings.find((warning) => String(warning).toLowerCase().includes("top hits")) ||
              "Simulation Drivers unavailable: no top_hits rows were returned in the current payload."
          : null,
    },
  };
}
