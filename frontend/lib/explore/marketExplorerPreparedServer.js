import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { preparedDirectoryResult, unavailablePreparedDirectory } from "./marketExplorerPreparedDirectory.mjs";

function safeBackendOrigin(baseUrl) {
  try { return new URL(baseUrl).origin; } catch { return "invalid-backend-url"; }
}

async function loadPreparedDirectory() {
  let backendBaseUrl = "";
  try {
    backendBaseUrl = getBackendApiBaseUrl();
    const response = await fetch(`${backendBaseUrl}/market/explorer/prepared-directory`, { next: { revalidate: 120 } });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const errorCode = typeof payload?.code === "string" ? payload.code : "PREPARED_DIRECTORY_BACKEND_FAILED";
      if (process.env.NODE_ENV !== "production") console.error("Market Explorer directory unavailable", { backendOrigin: safeBackendOrigin(backendBaseUrl), httpStatus: response.status, errorCode });
      return unavailablePreparedDirectory({ errorCode, httpStatus: response.status });
    }
    const result = preparedDirectoryResult(payload?.markets);
    if (result.status === "unavailable" && process.env.NODE_ENV !== "production") console.error("Market Explorer directory invalid response", { backendOrigin: safeBackendOrigin(backendBaseUrl), httpStatus: response.status, errorCode: result.errorCode });
    return result;
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.error("Market Explorer directory transport failure", { backendOrigin: safeBackendOrigin(backendBaseUrl), errorCode: "PREPARED_DIRECTORY_TRANSPORT_FAILED", errorName: error?.name || "Error" });
    return unavailablePreparedDirectory({ errorCode: "PREPARED_DIRECTORY_TRANSPORT_FAILED" });
  }
}

export const getMarketExplorerPreparedDirectory = cache(loadPreparedDirectory);
