import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

async function loadPreparedDirectory() {
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/market/explorer/prepared-directory`, { next: { revalidate: 120 } });
    if (!response.ok) return [];
    const payload = await response.json();
    return Array.isArray(payload?.markets) ? payload.markets : [];
  } catch {
    return [];
  }
}

export const getMarketExplorerPreparedDirectory = cache(loadPreparedDirectory);
