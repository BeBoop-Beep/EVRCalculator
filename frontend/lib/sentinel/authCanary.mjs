import { createHash } from "node:crypto";

export class AuthCanaryError extends Error {
  constructor(code) {
    super(code);
    this.name = "AuthCanaryError";
    this.code = code;
  }
}

function clean(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function positiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function loadAuthCanaryConfig(env = process.env) {
  const baseUrl = clean(env.SENTINEL_AUTH_CANARY_BASE_URL);
  const email = clean(env.SENTINEL_AUTH_CANARY_EMAIL);
  const password = clean(env.SENTINEL_AUTH_CANARY_PASSWORD);
  if (!baseUrl) throw new AuthCanaryError("auth_canary_base_url_missing");
  if (!email) throw new AuthCanaryError("auth_canary_email_missing");
  if (!password) throw new AuthCanaryError("auth_canary_password_missing");

  let parsed;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new AuthCanaryError("auth_canary_base_url_invalid");
  }
  const local = ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !(local && parsed.protocol === "http:")) {
    throw new AuthCanaryError("auth_canary_base_url_requires_https");
  }

  return {
    baseUrl: parsed.origin,
    email,
    password,
    timeoutMs: positiveInt(env.SENTINEL_AUTH_CANARY_TIMEOUT_MS, 20_000),
  };
}

export function safeAuthCanaryConfigSummary(config) {
  return {
    baseUrl: config.baseUrl,
    timeoutMs: config.timeoutMs,
    credentialsConfigured: Boolean(config.email && config.password),
  };
}

export function authIdentityFingerprint(user) {
  const source = clean(user?.id) || clean(user?.user_id) || clean(user?.email);
  if (!source) throw new AuthCanaryError("auth_canary_identity_missing");
  return createHash("sha256").update(source).digest("hex").slice(0, 16);
}

export function authenticatedUserFromPayload(status, payload) {
  if (Number(status) !== 200) {
    throw new AuthCanaryError("auth_canary_me_http_error");
  }
  if (!payload?.user || typeof payload.user !== "object") {
    throw new AuthCanaryError("auth_canary_me_payload_invalid");
  }
  return payload.user;
}

export const AUTH_CANARY_NAVIGATION = Object.freeze([
  { name: "Market", pathname: "/Market" },
  { name: "Rankings", pathname: "/Rankings" },
  { name: "TCGs", pathname: "/TCGs/Pokemon/Sets" },
]);

export function safeAuthCanaryFailure(error, stage) {
  return {
    status: "failed",
    stage: String(stage || "unknown"),
    code:
      error instanceof AuthCanaryError
        ? error.code
        : `auth_canary_${String(error?.name || "error").toLowerCase()}`,
  };
}
