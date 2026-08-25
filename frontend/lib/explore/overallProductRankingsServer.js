import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { normalizeOverallProductRankings } from "./overallProductRankingsNormalizer.mjs";

const BACKEND_URL = getBackendApiBaseUrl();
const ALLOWED_BUDGETS = new Set([
  "full_market", "25", "50", "100", "150", "250", "500", "750", "1000", "1250",
]);

export async function getOverallProductRankings(budget = "full_market") {
  const selected = ALLOWED_BUDGETS.has(String(budget)) ? String(budget) : "full_market";
  try {
    const url = new URL(`${BACKEND_URL}/explore/product-rankings/overall`);
    url.searchParams.set("budget", selected);
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return { status: "unavailable", reason: `http_${response.status}`, data: null };
    return normalizeOverallProductRankings(await response.json());
  } catch {
    return { status: "unavailable", reason: "request_failed", data: null };
  }
}
