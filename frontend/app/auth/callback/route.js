import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { exchangeSupabaseSession, setAppSessionCookie } from "@/lib/auth/appSession";
import { sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";

export async function GET(request) {
  const url = new URL(request.url);
  const next = sanitizeReturnPath(url.searchParams.get("next"));
  const errorRedirect = new URL("/login", url.origin);
  errorRedirect.searchParams.set("authError", "Unable to complete sign in. Please try again.");
  errorRedirect.searchParams.set("next", next);
  const code = url.searchParams.get("code");
  if (!code) return NextResponse.redirect(errorRedirect);

  try {
    const supabase = await createClient();
    const flowId = url.searchParams.get("sb_flow_id");
    const { data, error } = await supabase.auth.exchangeCodeForSession(code, flowId ? { flowId } : undefined);
    if (error || !data.session?.access_token) return NextResponse.redirect(errorRedirect);
    const exchange = await exchangeSupabaseSession(data.session.access_token);
    if (!exchange.ok || !exchange.token) {
      errorRedirect.searchParams.set("authError", exchange.payload?.message || "Unable to prepare your account.");
      return NextResponse.redirect(errorRedirect);
    }
    const response = NextResponse.redirect(new URL(next, url.origin));
    setAppSessionCookie(response, exchange.token);
    return response;
  } catch {
    return NextResponse.redirect(errorRedirect);
  }
}
