export function createRankingsSessionCache(identity, { now = () => Date.now() } = {}) {
  const entries = new Map();
  const inflight = new Map();
  function scoped(key) { return `${identity}:${key}`; }
  function peek(key) {
    const cacheKey = scoped(key);
    const entry = entries.get(cacheKey);
    if (!entry) return undefined;
    if (entry.expiresAt <= now()) { entries.delete(cacheKey); return undefined; }
    return entry.value;
  }
  return {
    identity,
    peek,
    has(key) { return peek(key) !== undefined; },
    async request(key, load, { force = false, maxAgeMs = key.startsWith("products:") ? 60_000 : Infinity } = {}) {
      const cacheKey = scoped(key);
      const cached = peek(key);
      if (!force && cached !== undefined) return cached;
      if (!force && inflight.has(cacheKey)) return inflight.get(cacheKey);
      const promise = Promise.resolve().then(load).then((value) => {
        // A forced refresh or auth/publication invalidation may have superseded
        // this request. Its response must never repopulate the cache afterward.
        if (inflight.get(cacheKey) === promise) {
          entries.set(cacheKey, { value, expiresAt: now() + maxAgeMs });
        }
        return value;
      }).finally(() => {
        if (inflight.get(cacheKey) === promise) inflight.delete(cacheKey);
      });
      inflight.set(cacheKey, promise);
      return promise;
    },
    isPending(key) { return inflight.has(scoped(key)); },
    clear() { entries.clear(); inflight.clear(); },
  };
}

export function canonicalCardQueryKey(params, lens = "chase") {
  return `cards:${lens}:${new URLSearchParams([...params.entries()].sort(([a], [b]) => a.localeCompare(b))).toString()}`;
}
