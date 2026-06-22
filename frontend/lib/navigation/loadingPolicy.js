export const FULL_LOADER_DELAY_MS = 700;
export const MIN_FULL_LOADER_VISIBLE_MS = 400;
export const LIGHTWEIGHT_FEEDBACK_MIN_VISIBLE_MS = 150;
export const LIGHTWEIGHT_FEEDBACK_MAX_VISIBLE_MS = 10000;

export function debugLoadingTiming(label, details = {}) {
  if (process.env.NODE_ENV === "production") {
    return;
  }
  console.debug(`[loading-policy] ${label}`, details);
}

export function announceNavigationStart(details = {}) {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(
    new CustomEvent("index:navigation-start", {
      detail: details,
    })
  );
}
