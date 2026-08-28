import { cache } from "react";

import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { normaliseRipStatisticsTarget } from "@/lib/explore/ripStatisticsNormalizer.mjs";

const BACKEND_API_BASE_URL = getBackendApiBaseUrl();

const loadDirectory = cache(async (limit = 150) => {
  const url = new URL(`${BACKEND_API_BASE_URL}/tcgs/pokemon/set-route-directory`);
  url.searchParams.set("limit", String(limit));
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    next: { revalidate: 300, tags: ["pokemon-set-route-directory"] },
  });
  if (!response.ok) throw new Error(`Set route directory backend error ${response.status}`);
  const payload = await response.json();
  return {
    ...payload,
    targets: Array.isArray(payload?.targets)
      ? payload.targets.map(normaliseRipStatisticsTarget)
      : [],
    default_target: normaliseRipStatisticsTarget(payload?.default_target || null),
  };
});

export async function getPokemonSetRouteDirectory({ limit = 150 } = {}) {
  return loadDirectory(limit);
}
