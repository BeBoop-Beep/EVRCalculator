export class BillingClientError extends Error {
  constructor(message, status, code) { super(message); this.name = "BillingClientError"; this.status = status; this.code = code; }
}
async function request(path, init = {}) {
  const response = await fetch(path, { ...init, credentials: "include", cache: "no-store",
    headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers || {}) } });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) { const detail = payload?.detail || payload; throw new BillingClientError("Billing request could not be completed.", response.status, detail?.code || "BILLING_REQUEST_FAILED"); }
  return payload;
}
export function getBillingStatus(options = {}) { return request("/api/billing/me", { signal: options.signal }); }
export function createCheckoutSession(offerKey) { return request("/api/billing/checkout-session", { method: "POST", body: JSON.stringify({ offerKey }) }); }
export function createCustomerPortalSession() { return request("/api/billing/customer-portal", { method: "POST" }); }
