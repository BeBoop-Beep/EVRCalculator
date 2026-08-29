export function createRankingsSessionCache(identity) {
  const entries = new Map();
  const inflight = new Map();

  function scoped(key) { return `${identity}:${key}`; }

  return {
    identity,
    peek(key) { return entries.get(scoped(key)); },
    has(key) { return entries.has(scoped(key)); },
    async request(key, load, { force = false } = {}) {
      const cacheKey = scoped(key);
      if (!force && entries.has(cacheKey)) return entries.get(cacheKey);
      if (!force && inflight.has(cacheKey)) return inflight.get(cacheKey);
      const promise = Promise.resolve().then(load).then((value) => {
        entries.set(cacheKey, value);
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

export function canonicalCardQueryKey(params) {
  return `cards:${new URLSearchParams([...params.entries()].sort(([a], [b]) => a.localeCompare(b))).toString()}`;
}
