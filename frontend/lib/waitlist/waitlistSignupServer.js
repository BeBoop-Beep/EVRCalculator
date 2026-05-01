import { getPublicBackendApiBaseUrl } from "@/lib/runtimeUrls";

/**
 * waitlistSignupServer.js
 *
 * Dedicated client-side helper for the landing page waitlist signup.
 * Calls POST /waitlist/signup on the Python backend directly.
 *
 * Isolation guarantees:
 *   - No auth tokens sent or read
 *   - No session cookies written
 *   - No connection to Explore, portfolio, profile, or collection APIs
 *
 * @typedef {"created" | "verification_pending" | "verified" | "already_exists" | "already_verified" | "invalid_email" | "invalid_or_expired" | "server_error"} WaitlistStatus
 *
 * @typedef {{ status: WaitlistStatus; message?: string }} WaitlistResult
 */

const EMAIL_RE = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{3,}$/i;

const BACKEND_API_BASE_URL = getPublicBackendApiBaseUrl();

export function isLikelyValidEmail(email) {
  return EMAIL_RE.test(String(email || "").trim());
}

/**
 * Submit an email address to the waitlist.
 *
 * @param {string} email
 * @param {string} [source]
 * @returns {Promise<WaitlistResult>}
 */
export async function submitWaitlistSignup(email, source = "landing_page") {
  try {
    const res = await fetch(`${BACKEND_API_BASE_URL}/waitlist/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), source }),
    });

    const data = await res.json().catch(() => ({}));

    // The backend returns { status: "created" | "already_exists" } on 200,
    // or { status: "invalid_email" | "server_error", message: "..." } on 4xx/5xx.
    if (data.status) {
      return { status: data.status, message: data.message };
    }

    // Fallback if the backend response is missing a status field.
    return res.ok
      ? { status: "created" }
      : {
          status: "server_error",
          message: data.message || "Something went wrong. Please try again.",
        };
  } catch {
    return { status: "server_error", message: "Unable to connect. Please try again." };
  }
}

/**
 * Verify a raw waitlist token from email link.
 *
 * @param {string} token
 * @returns {Promise<WaitlistResult>}
 */
export async function verifyWaitlistSignupToken(token) {
  try {
    const res = await fetch(`${BACKEND_API_BASE_URL}/waitlist/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: String(token || "").trim() }),
    });

    const data = await res.json().catch(() => ({}));
    if (data.status) {
      return { status: data.status, message: data.message };
    }

    return res.ok
      ? { status: "created" }
      : {
          status: "server_error",
          message: data.message || "Something went wrong. Please try again.",
        };
  } catch {
    return { status: "server_error", message: "Unable to connect. Please try again." };
  }
}
