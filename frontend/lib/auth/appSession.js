import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const APP_COOKIE_NAME = "token";
export const APP_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax",
  maxAge: 60 * 60 * 24,
  path: "/",
};

export function setAppSessionCookie(response, token) {
  response.cookies.set(APP_COOKIE_NAME, token, APP_COOKIE_OPTIONS);
}

export function clearAppSessionCookie(response) {
  response.cookies.set(APP_COOKIE_NAME, "", { ...APP_COOKIE_OPTIONS, expires: new Date(0), maxAge: 0 });
}

export async function exchangeSupabaseSession(accessToken) {
  const backendResponse = await fetch(`${getBackendApiBaseUrl()}/auth/supabase/exchange`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
    cache: "no-store",
  });
  const payload = await backendResponse.json().catch(() => ({}));
  return { ok: backendResponse.ok, status: backendResponse.status, token: payload.token, payload };
}

export function appSessionJson(exchange) {
  const safePayload = { ...exchange.payload };
  delete safePayload.token;
  const response = NextResponse.json(safePayload, { status: exchange.status });
  if (exchange.ok && exchange.token) setAppSessionCookie(response, exchange.token);
  return response;
}
