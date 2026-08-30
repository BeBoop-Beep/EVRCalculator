export function marketSeedMatchesSet(payload, setId) {
  if (!payload || !setId) return false;
  const wanted = String(setId).trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
  const identity = payload.set || payload.setIdentity || payload.set_identity || {};
  return [identity.id, identity.set_id, identity.slug, identity.canonical_key]
    .filter(Boolean)
    .some((value) => String(value).trim().toLowerCase().replace(/[^a-z0-9]+/g, "") === wanted);
}

export function createMarketModuleState(setId, seed = null) {
  return { status: seed ? "success" : "idle", setId, payload: seed, error: null };
}

export function readLatestSetValue(history) {
  const points = Array.isArray(history) ? history : [];
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    const value = Number(point?.setValue ?? point?.set_value ?? point?.value);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

export function selectMarketAsOfDate(...payloads) {
  const dates = payloads.flatMap((payload) => [
    payload?.latestMarketDate,
    payload?.latest_market_date,
    payload?.meta?.snapshot?.marketAsOfDate,
    payload?.meta?.snapshot?.market_as_of_date,
  ]).filter(Boolean).map(String).sort();
  return dates.at(-1) || null;
}
