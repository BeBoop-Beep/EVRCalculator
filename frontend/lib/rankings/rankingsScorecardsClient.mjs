const ENDPOINT = "/api/tcgs/pokemon/rankings/scorecards";

async function json(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.detail?.message || payload?.message || "Rankings scorecards request failed");
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function readRankingsScorecards(entityType, { fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  if (!["set", "era"].includes(entityType)) throw new Error("entityType must be set or era");
  const cacheKey = `rankings:scorecards:${entityType}`;
  const load = () => fetchImpl(`${ENDPOINT}?entity_type=${entityType}`, { credentials: "include", cache: "no-store" }).then(json);
  return sessionCache ? sessionCache.request(cacheKey, load, { force }) : load();
}

export function scorecardSetTarget(row) {
  return {
    target_type: "set", target_id: row?.entityId, setId: row?.entityId,
    name: row?.name, canonical_key: row?.canonicalKey,
    era: row?.era?.eraName, eraId: row?.era?.eraId,
    logo_image_url: row?.logoImageUrl, symbol_image_url: row?.symbolImageUrl,
  };
}
