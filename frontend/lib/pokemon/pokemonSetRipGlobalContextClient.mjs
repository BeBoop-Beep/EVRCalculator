export async function getPokemonSetRipGlobalContext(setId, { expectedCalculationRunId, signal } = {}) {
  const id = String(setId || "").trim();
  if (!id) throw new Error("setId is required");
  const url = new URL(`/api/tcgs/pokemon/sets/${encodeURIComponent(id)}/rip/global-context`, window.location.origin);
  if (expectedCalculationRunId) url.searchParams.set("expected_calculation_run_id", expectedCalculationRunId);
  const response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) throw new Error(`Set RIP global context request failed (${response.status})`);
  return response.json();
}

export function selectCompatibleSetRipGlobalContext(payload, expectedCalculationRunId) {
  if (!payload || payload.compatible !== true || payload.status !== "ready") return null;
  if (expectedCalculationRunId && String(payload.expectedCalculationRunId || "") !== String(expectedCalculationRunId)) return null;
  return payload;
}
