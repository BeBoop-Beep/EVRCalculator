const startFor = (endDate, days) => {
  const value = new Date(`${endDate}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
};
const change = (value, startDate, endDate) => value == null ? { available: false } : {
  available: true, percent: Number(value), startDate, endDate,
};

// Server-computed long-window returns, keyed exactly like
// compute_strict_window_movements (1D/7D/30D/3M/6M/1Y/SinceTracking) --
// see backend/db/services/market_explorer_prepared_directory.py's
// read_prepared_comparison_bundle. Falls back to the row-level 7D/30D/90D/1Y
// columns (with SinceTracking genuinely unavailable) only if a caller
// somehow still hands this the un-enriched `read_prepared_comparison` shape
// with no `window_movements` at all -- never a fabricated 0%.
function resolveChanges(row) {
  const movements = row.window_movements;
  if (movements && typeof movements === "object" && Object.keys(movements).length) return movements;
  const end = row.comparison_as_of;
  return {
    "7D": change(row.return_7d_pct, startFor(end, 7), end), "30D": change(row.return_30d_pct, startFor(end, 30), end),
    "3M": change(row.return_90d_pct, startFor(end, 90), end), "1Y": change(row.return_1y_pct, startFor(end, 365), end),
    SinceTracking: change(null),
  };
}

// A Set or Era name alone is ambiguous once Sealed markets exist ("Fossil" is both a
// Cards market and a Sealed market). The asset comes from the PUBLISHED row
// (`asset`), never from parsing the market key, and only Set/Era identities are
// qualified so globally unique names ("Total Sealed", "Top 10") stay quiet.
export function assetContextLabel(row) {
  const label = row?.label;
  if (!label) return label;
  // Sets, Eras, Rarity markets and Sealed Types share names across assets ("Fossil",
  // "Booster Boxes" vs a Cards rarity), so each is qualified from its published asset.
  const scoped = ["set", "era", "prepared_rarity", "prepared_format"].includes(row.market_type)
    || ["set", "era", "rarity", "type"].includes(row.scope_kind);
  if (!scoped) return label;
  const suffix = row.asset === "sealed" ? "Sealed" : "Cards";
  return label.toLowerCase().includes(suffix.toLowerCase()) ? label : `${label} — ${suffix}`;
}

export function buildPreparedSeries(rows = [], history = []) {
  const historyByKey = new Map();
  for (const point of history) {
    const key = point.requested_market_key || point.market_key;
    if (!historyByKey.has(key)) historyByKey.set(key, []);
    historyByKey.get(key).push({ date: point.market_date, value: Number(point.index_value), trackedValue: point.tracked_value == null ? null : Number(point.tracked_value) });
  }
  return rows.map((row) => {
    const end = row.comparison_as_of;
    const changes = resolveChanges(row);
    // A legacy alias resolved server-side keeps the REQUESTED key as its
    // workspace identity; the canonical key rides along for the pager.
    const seriesKey = row.requested_market_key || row.market_key;
    const color = resolveSeriesIdentityColor(seriesKey, seriesKey);
    return {
      key: seriesKey, canonicalMarketKey: row.market_key, label: row.label, shortLabel: assetContextLabel(row), group: row.asset === "sealed" ? "sealed" : "card",
      // PREPARED IDENTITY, published by the backend on the directory row and
      // carried verbatim for the constituent pager. Nothing here is derived from
      // labels or key strings. `generationId` pins paging to this exact
      // publication; a mismatch is reloaded, never mixed.
      asset: row.asset === "sealed" ? "sealed" : "cards", generationId: row.generation_id ?? null,
      preparedSeriesKey: row.prepared_series_key ?? null, sourceKind: row.source_kind ?? null,
      marketScope: row.metadata?.marketScope || "standard", baseSetName: row.metadata?.baseSetName ?? null,
      marketType: row.market_type, setId: row.set_id, eraId: row.era_id, parentEraId: row.parent_era_id,
      available: row.available !== false, historyAvailable: row.history_available,
      // V2-published composition + availability metadata (undefined for V1 rows).
      compositionKind: row.composition_kind ?? undefined, availability: row.availability ?? undefined,
      unavailableReason: row.unavailable_reason ?? null, scopeKind: row.scope_kind ?? null,
      surfaceVersion: row.surface_version ?? null, basketValue: row.comparison_value,
      browseValue: row.current_value, sourceAsOf: row.source_as_of, comparisonAsOf: end,
      indexValue: row.comparison_index_value, historyStartDate: row.history_start_date,
      trend: historyByKey.get(seriesKey) || [], changes, familyChanges: changes,
      // Only a compact, identity-keyed authority (query-cache fingerprint
      // match) ever populates this server-side -- never a "latest" guess.
      // `null` renders as "-" in MarketExplorerDetails, which is correct
      // when the count cannot be proven to match this comparison's as-of.
      constituentCount: row.constituent_count ?? null,
      analytics: {
        currentDrawdown: row.current_drawdown_pct, maxDrawdown: row.max_drawdown_pct,
        relative7D: row.relative_7d_vs_era_pct, relative30D: row.relative_30d_vs_era_pct,
        relative90D: row.relative_90d_vs_era_pct, relative1Y: row.relative_1y_vs_era_pct,
      },
      sourceStatus: row.source_status, metadata: row.metadata || {},
      color, softColor: softSeriesColor(color),
    };
  });
}

/**
 * Fetch ONE prepared market (its directory row + its own history) and build its
 * series. `contextKeys` are the other markets already on the chart; the backend
 * uses them only to judge the Index+ compare entitlement and never reads them.
 * A market the backend does not return is an INVALID_KEY failure, never a
 * silently empty success.
 */
export async function fetchPreparedMarket(key, { contextKeys = [], signal } = {}) {
  const response = await fetch("/api/market/explorer/prepared", {
    method: "POST", credentials: "include", cache: "no-store", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marketKeys: [key], contextMarketKeys: contextKeys.slice(0, 25) }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail && typeof payload.detail === "object" ? payload.detail : null;
    throw new PreparedFetchError("Prepared market request failed", {
      status: response.status, code: payload?.code || detail?.code || "",
    });
  }
  const rows = (Array.isArray(payload?.markets) ? payload.markets : []).filter((row) => row.market_key === key || row.requested_market_key === key);
  const history = (Array.isArray(payload?.history) ? payload.history : []).filter((point) => point.market_key === key || point.requested_market_key === key);
  const [series] = buildPreparedSeries(rows, history);
  if (!series) throw new PreparedFetchError("Unknown prepared market", { status: 404, code: "PREPARED_MARKET_UNKNOWN" });
  return series;
}

export const QUICK_MARKET_KEYS = Object.freeze([
  "curated:obtainable", "curated:intermediate", "curated:premium",
  "curated:new-releases", "curated:established", "curated:global-top10",
]);

export function normalizePreparedDirectorySearch(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function groupPreparedDirectory(rows = [], search = "") {
  const terms = normalizePreparedDirectorySearch(search).split(" ").filter(Boolean);
  const visible = rows.filter((row) => {
    if (!terms.length) return true;
    const label = normalizePreparedDirectorySearch(row.label);
    return terms.every((term) => label.includes(term));
  });
  const eras = visible.filter((row) => row.market_type === "era").sort((a, b) => a.label.localeCompare(b.label));
  const eraById = new Map(rows.filter((row) => row.market_type === "era").map((row) => [row.era_id, row]));
  const sets = new Map();
  for (const row of visible.filter((item) => item.market_type === "set").sort((a, b) => a.label.localeCompare(b.label))) {
    const era = eraById.get(row.parent_era_id);
    const key = era?.market_key || `era:${row.parent_era_id}`;
    if (!sets.has(key)) sets.set(key, { era, rows: [] });
    sets.get(key).rows.push(row);
  }
  const quick = QUICK_MARKET_KEYS.map((key) => visible.find((row) => row.market_key === key)).filter(Boolean);
  // Whole-asset parents (Raw Card Market / Total Sealed): published V2 directory rows,
  // listed first under Sets so the whole market stays selectable after Clear All.
  const parents = visible.filter((row) => row.market_type === "parent");
  return { parents, eras, sets: [...sets.values()].sort((a, b) => (a.era?.label || "").localeCompare(b.era?.label || "")), quick };
}
import { resolveSeriesIdentityColor, softSeriesColor } from "./marketExplorerSeriesColors.mjs";
import { PreparedFetchError } from "./marketExplorerPreparedLoader.mjs";

/**
 * The ACTUAL published prepared Sealed markets (asset 'sealed', e.g. Booster
 * Boxes / Elite Trainer Boxes / Packs prepared_format rows), searchable by
 * label. Nothing here is synthesised: an empty directory yields an empty list,
 * and card Sets/Eras are never re-labelled as Sealed.
 */
export function listPreparedSealedMarkets(rows = [], search = "") {
  const terms = normalizePreparedDirectorySearch(search).split(" ").filter(Boolean);
  return rows
    .filter((row) => row?.asset === "sealed")
    .filter((row) => {
      if (!terms.length) return true;
      const label = normalizePreparedDirectorySearch(row.label);
      return terms.every((term) => label.includes(term));
    })
    .sort((a, b) => String(a.label).localeCompare(String(b.label)));
}
