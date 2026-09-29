import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_URL = getBackendApiBaseUrl();

async function publicJson(path, fallback, fetchOptions = { cache: "no-store" }) {
  try {
    const response = await fetch(`${BACKEND_URL}${path}`, { ...fetchOptions, headers: { Accept: "application/json" } });
    if (!response.ok) return fallback;
    const payload = await response.json();
    return payload && typeof payload === "object" ? payload : fallback;
  } catch { return fallback; }
}

export const getRankingsOverview = cache(() => publicJson(
  "/tcgs/pokemon/rankings/overview-v2",
  { contractVersion: "rankings-overview-v2", status: "unavailable" },
));

export const getFinancialCohort = cache(() => publicJson(
  "/tcgs/pokemon/rankings/financial-cohort",
  { contractVersion: "financial-rip-cohort-v1", eras: [] },
  { next: { revalidate: 300 } },
));
