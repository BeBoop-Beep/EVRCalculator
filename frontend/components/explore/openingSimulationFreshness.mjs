import { getHistoryDateKey } from "./historyDateFormatting.mjs";

// Opening Profit vs Cost is produced by the simulation batch, while every other
// market surface on the page is produced by the daily scrape. The two clocks can
// diverge — in production they diverged by five days — and when they do, the
// section must say so plainly rather than let the chart imply the simulation
// kept pace with the market.
//
// This is a freshness statement, not a diagnostic: it names dates, never
// pipeline internals.

function formatDisplayDate(dateKey) {
  const key = getHistoryDateKey(dateKey);
  if (!key) return null;
  const [year, month, day] = key.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * Build the Opening Profit vs Cost freshness line.
 *
 * @param {string|null} latestRealSimulationDate Last date backed by an actual
 *   simulation run. Carried-forward chart points must never be passed here.
 * @param {string|null} marketAsOfDate Canonical market date for the page.
 * @returns {{
 *   simulationAsOfDate: string|null,
 *   marketAsOfDate: string|null,
 *   isStale: boolean,
 *   label: string|null,
 *   accessibleLabel: string|null,
 * }}
 */
export function buildOpeningSimulationFreshness({
  latestRealSimulationDate = null,
  marketAsOfDate = null,
} = {}) {
  const simulationDate = getHistoryDateKey(latestRealSimulationDate);
  const marketDate = getHistoryDateKey(marketAsOfDate);

  if (!simulationDate) {
    return {
      simulationAsOfDate: null,
      marketAsOfDate: marketDate,
      isStale: false,
      label: null,
      accessibleLabel: null,
    };
  }

  const isStale = Boolean(marketDate && simulationDate < marketDate);
  const simulationDisplay = formatDisplayDate(simulationDate);
  const marketDisplay = formatDisplayDate(marketDate);

  const label = isStale && marketDisplay
    ? `Simulation as of ${simulationDisplay} · market data through ${marketDisplay}`
    : `Simulation as of ${simulationDisplay}`;

  const accessibleLabel = isStale && marketDisplay
    ? `Opening profit versus cost was last simulated on ${simulationDisplay}. Market data is current through ${marketDisplay}.`
    : `Opening profit versus cost was last simulated on ${simulationDisplay}.`;

  return {
    simulationAsOfDate: simulationDate,
    marketAsOfDate: marketDate,
    isStale,
    label,
    accessibleLabel,
  };
}
