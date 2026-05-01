const DEV_BACKEND_API_BASE_URL = "http://127.0.0.1:8000";
const DEV_SITE_BASE_URL = "http://localhost:3000";

function isProductionRuntime() {
  return process.env.NODE_ENV === "production";
}

function normalizeBaseUrl(value, envVarName) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    throw new Error(`${envVarName} must be configured.`);
  }
  return normalized.replace(/\/$/, "");
}

export function getBackendApiBaseUrl() {
  const configured = process.env.BACKEND_API_BASE_URL;
  if (configured) {
    return normalizeBaseUrl(configured, "BACKEND_API_BASE_URL");
  }
  if (isProductionRuntime()) {
    throw new Error("BACKEND_API_BASE_URL must be configured in production.");
  }
  return DEV_BACKEND_API_BASE_URL;
}

export function getPublicBackendApiBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL;
  if (configured) {
    return normalizeBaseUrl(configured, "NEXT_PUBLIC_BACKEND_API_BASE_URL");
  }
  if (isProductionRuntime()) {
    throw new Error("NEXT_PUBLIC_BACKEND_API_BASE_URL must be configured in production.");
  }
  return DEV_BACKEND_API_BASE_URL;
}

export function getFrontendBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_BASE_URL;
  if (configured) {
    return normalizeBaseUrl(configured, "NEXT_PUBLIC_BASE_URL");
  }
  if (isProductionRuntime()) {
    throw new Error("NEXT_PUBLIC_BASE_URL must be configured in production.");
  }
  return DEV_SITE_BASE_URL;
}