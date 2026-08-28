export const DIRECTORY_LKG_MAX_ENTRIES = 4;

export function cloneDirectory(payload) { return JSON.parse(JSON.stringify(payload)); }
export function isValidCanonicalDirectory(payload) {
  return Array.isArray(payload?.targets) && payload.targets.length > 0 && payload.default_target && typeof payload.default_target === "object";
}
export function createRouteDirectoryLkg(maxEntries = DIRECTORY_LKG_MAX_ENTRIES) {
  const entries = new Map();
  return {
    entries,
    remember(limit, payload) {
      if (!isValidCanonicalDirectory(payload)) return false;
      entries.delete(limit); entries.set(limit, cloneDirectory(payload));
      while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
      return true;
    },
    fallback(limit, fallbackAt = new Date().toISOString()) {
      const stored = entries.get(limit); if (!stored) return null;
      const payload = cloneDirectory(stored);
      payload.meta = { ...(payload.meta || {}), stale: true, fallback: true, fallbackReason: "route_directory_transport_failure", fallbackAt };
      return payload;
    },
  };
}
