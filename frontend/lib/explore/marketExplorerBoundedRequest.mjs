// One shared bounded-execution primitive for query-backed Explorer lanes
// (Custom Filters, Exact Basket, rarity fallback, edits). Same approach as the
// 2A prepared loader: an AbortController armed with a timeout, plus an
// optional caller signal. It ALWAYS settles: a response, an error, or an abort.
export const QUERY_REQUEST_TIMEOUT_MS = 45000;
export const EXPLORER_REQUEST_BOUNDS_MS = Object.freeze({
  directory: 4000,
  search: 9000,
  screen: 4000,
  prepared: 14000,
  constituents: 14000,
  assetOptions: 9000,
  directInstrument: 8000,
  activity: 6000,
  customBuild: QUERY_REQUEST_TIMEOUT_MS,
});

export class BoundedRequestError extends Error {
  constructor(message, { timedOut = false, aborted = false } = {}) {
    super(message);
    this.name = "BoundedRequestError";
    this.timedOut = timedOut;
    this.aborted = aborted;
    this.code = timedOut ? "QUERY_TIMEOUT" : aborted ? "QUERY_ABORTED" : "QUERY_FAILED";
  }
}

export async function boundedFetch(url, init = {}, { timeoutMs = QUERY_REQUEST_TIMEOUT_MS, timeoutMessage = "Request timed out. Please try again.", timeoutCode = "QUERY_TIMEOUT", signal, read, fetchImpl = fetch, setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  const timer = setTimer(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetchImpl(url, { ...init, signal: controller.signal });
    // The body read stays inside the same bound: a stalled body must not hang.
    return read ? { response, payload: await read(response) } : response;
  } catch (error) {
    if (timedOut) {
      const bounded = new BoundedRequestError(timeoutMessage, { timedOut: true });
      bounded.code = timeoutCode;
      throw bounded;
    }
    if (controller.signal.aborted) throw new BoundedRequestError("Request cancelled.", { aborted: true });
    throw error;
  } finally {
    clearTimer(timer);
    signal?.removeEventListener?.("abort", onAbort);
  }
}
