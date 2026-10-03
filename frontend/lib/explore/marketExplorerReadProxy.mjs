export const EXPLORER_PROXY_BOUNDS_MS = Object.freeze({
  prepared: 11000,
  constituents: 11000,
  assetOptions: 6500,
  catalogSearch: 6500,
});

const TRANSIENT_CODES = new Set([
  "PGRST002",
  "PREPARED_COMPARISON_FAILED",
  "PREPARED_PROXY_UNAVAILABLE",
  "SURFACE_V2_DIRECTORY_FAILED",
  "SURFACE_V2_HISTORY_FAILED",
  "SURFACE_V2_CONSTITUENTS_FAILED",
  "ASSET_OPTIONS_FAILED",
  "ASSET_OPTIONS_PROXY_UNAVAILABLE",
  "CATALOG_SEARCH_FAILED",
  "CATALOG_SEARCH_PROXY_UNAVAILABLE",
]);

export function isRetryableExplorerRead({ status, code, error } = {}) {
  if (error) return error?.name !== "AbortError";
  return [502, 503].includes(Number(status)) && TRANSIENT_CODES.has(String(code || ""));
}
const abortError = () => new DOMException("aborted", "AbortError");

/** One total proxy deadline and at most one retry; attempts never stack bounds. */
export async function fetchExplorerRead({
  url, init = {}, timeoutMs, operation, requestSignal, fetchImpl = fetch,
  now = () => Date.now(), setTimer = setTimeout, clearTimer = clearTimeout,
}) {
  const started = now();
  let attempts = 0;
  let lastError = null;
  while (attempts < 2) {
    attempts += 1;
    const remaining = timeoutMs - (now() - started);
    if (remaining <= 0) throw Object.assign(abortError(), { proxyTimedOut: true, attempts });
    const controller = new AbortController();
    let timedOut = false;
    const onAbort = () => controller.abort();
    requestSignal?.addEventListener?.("abort", onAbort, { once: true });
    const timer = setTimer(() => { timedOut = true; controller.abort(); }, remaining);
    try {
      const response = await fetchImpl(url, { ...init, signal: controller.signal, cache: "no-store" });
      const text = typeof response.text === "function"
        ? await response.text()
        : JSON.stringify(await response.json());
      let payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch { payload = null; }
      const code = payload?.code || payload?.detail?.code || "";
      if (attempts === 1 && isRetryableExplorerRead({ status: response.status, code })) continue;
      return { response, text, payload, attempts, elapsedMs: now() - started, operation };
    } catch (error) {
      lastError = error;
      if (requestSignal?.aborted) throw error;
      if (timedOut) throw Object.assign(error, { proxyTimedOut: true, attempts });
      if (attempts === 1 && isRetryableExplorerRead({ error })) continue;
      throw Object.assign(error, { attempts });
    } finally {
      clearTimer(timer);
      requestSignal?.removeEventListener?.("abort", onAbort);
    }
  }
  throw lastError || new Error(`${operation} failed`);
}
