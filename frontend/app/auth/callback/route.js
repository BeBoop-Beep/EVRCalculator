import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { exchangeSupabaseSession, setAppSessionCookie } from "@/lib/auth/appSession";
import { sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";
import { OAUTH_RETURN_COOKIE, resolveCallbackNext } from "@/lib/auth/oauthState.mjs";

function clearReturnCookie(response) {
  response.cookies.set(OAUTH_RETURN_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}

export async function GET(request) {
  const url = new URL(request.url);
  const next = resolveCallbackNext({
    queryNext: url.searchParams.get("next"),
    cookieNext: request.cookies.get(OAUTH_RETURN_COOKIE)?.value,
  });
  const errorRedirect = new URL("/login", url.origin);
  errorRedirect.searchParams.set("authError", "Unable to complete sign in. Please try again.");
  errorRedirect.searchParams.set("next", next);

  // Supabase redirects here with `error`/`error_description` instead of `code`
  // when the provider step failed or the user cancelled. Surface a generic
  // message only — never forward the raw error/description or any token into
  // the URL the browser lands on.
  const providerError = url.searchParams.get("error");
  const code = url.searchParams.get("code");
  if (providerError || !code) {
    return clearReturnCookie(NextResponse.redirect(errorRedirect));
  }

  try {
    const supabase = await createClient();
    const flowId = url.searchParams.get("sb_flow_id");
    const { data, error } = await supabase.auth.exchangeCodeForSession(code, flowId ? { flowId } : undefined);
    if (error || !data.session?.access_token) return clearReturnCookie(NextResponse.redirect(errorRedirect));
    const exchange = await exchangeSupabaseSession(data.session.access_token);
    if (!exchange.ok || !exchange.token) {
      errorRedirect.searchParams.set("authError", exchange.payload?.message || "Unable to prepare your account.");
      return clearReturnCookie(NextResponse.redirect(errorRedirect));
    }
    const response = NextResponse.redirect(new URL(sanitizeReturnPath(next), url.origin));
    setAppSessionCookie(response, exchange.token);
    return clearReturnCookie(response);
  } catch {
    return clearReturnCookie(NextResponse.redirect(errorRedirect));
  }
}
