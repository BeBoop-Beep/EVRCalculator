import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { appSessionJson, exchangeSupabaseSession } from "@/lib/auth/appSession";
import { buildAuthCallbackUrlWithNext, sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";
import { getFrontendBaseUrl } from "@/lib/runtimeUrls";

export async function POST(request) {
  try {
    const body = await request.json();
    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!email || password.length < 8) return NextResponse.json({ message: "A valid email and password are required." }, { status: 400 });
    const next = sanitizeReturnPath(body.next);
    // The confirmation link is server-generated, so it must not be built from an
    // arbitrary request Host header — use the configured, trusted application
    // origin instead (client-initiated OAuth uses window.location.origin, a
    // different trust model; see lib/auth/returnPath.mjs).
    const callback = buildAuthCallbackUrlWithNext(getFrontendBaseUrl(), next);
    const { data, error } = await (await createClient()).auth.signUp({ email, password, options: { emailRedirectTo: callback } });
    if (error) return NextResponse.json({ message: "Unable to create the account. Check your details and try again." }, { status: 400 });
    if (!data.session) return NextResponse.json({ message: "Check your email to confirm your account.", requiresEmailConfirmation: true }, { status: 201 });
    return appSessionJson(await exchangeSupabaseSession(data.session.access_token));
  } catch {
    return NextResponse.json({ message: "Authentication service is unavailable." }, { status: 503 });
  }
}
