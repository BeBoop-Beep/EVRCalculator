// One shared bounded-execution primitive for query-backed Explorer lanes
// (Custom Filters, Exact Basket, rarity fallback, edits). Same approach as the
// 2A prepared loader: an AbortController armed with a timeout, plus an
// optional caller signal. It ALWAYS settles: a response, an error, or an abort.
export const QUERY_REQUEST_TIMEOUT_MS = 45000;

export class BoundedRequestError extends Error {
  constructor(message, { timedOut = false, aborted = false } = {}) {
    super(message);
    this.name = "BoundedRequestError";
    this.timedOut = timedOut;
    this.aborted = aborted;
    this.code = timedOut ? "QUERY_TIMEOUT" : aborted ? "QUERY_ABORTED" : "QUERY_FAILED";
  }
}

export async function boundedFetch(url, init = {}, { timeoutMs = QUERY_REQUEST_TIMEOUT_MS, signal, read, fetchImpl = fetch, setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
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
    if (timedOut) throw new BoundedRequestError("This market took too long to build. Please try again.", { timedOut: true });
    if (controller.signal.aborted) throw new BoundedRequestError("Request cancelled.", { aborted: true });
    throw error;
  } finally {
    clearTimer(timer);
    signal?.removeEventListener?.("abort", onAbort);
  }
}
