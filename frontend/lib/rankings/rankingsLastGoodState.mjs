export function beginLastGoodRefresh(current, isRenderable) {
  if (isRenderable(current)) {
    return { ...current, status: "ready", refreshing: true, refreshError: null };
  }
  return { ...current, status: "loading", refreshing: false, refreshError: null };
}

export function failLastGoodRefresh(current, error, isRenderable, emptyState) {
  const message = error?.message || String(error || "Request failed");
  if (isRenderable(current)) {
    return { ...current, status: "ready", refreshing: false, refreshError: message };
  }
  return { ...emptyState, status: "error", error: message, refreshing: false, refreshError: null };
}

export const isRenderableEraState = (state) =>
  state?.status === "ready" && Boolean(state?.contract) && Boolean(state?.benchmark);

export const isRenderableSetState = (state) =>
  state?.status === "ready" && Array.isArray(state?.targets) && state.targets.length > 0 && Boolean(state?.benchmark);

export const isRenderableProductState = (state) =>
  state?.status === "ready" && Boolean(state?.productFamilyRankings);
