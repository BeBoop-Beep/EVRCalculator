const ENDPOINT = "/api/tcgs/pokemon/rankings/pack-economics";

async function json(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.detail?.message || payload?.message || "Pack Economics request failed");
    error.status = response.status;
    throw error;
  }
  return payload;
}

export function readPackEconomics({ fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  const load = () => fetchImpl(ENDPOINT, { credentials: "include", cache: "no-store" }).then(json);
  return sessionCache ? sessionCache.request("sets:pack-economics", load, { force }) : load();
}
