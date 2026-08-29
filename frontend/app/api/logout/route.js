import { NextResponse } from "next/server";
import { clearAppSessionCookie } from "@/lib/auth/appSession";
import { createClient } from "@/lib/supabase/server";

export async function POST() {
  try {
    const supabase = await createClient();
    await supabase.auth.signOut({ scope: "local" });
  } catch {
    // The inDex session is still cleared when Supabase is unavailable/unconfigured.
  }
  const response = NextResponse.json({ message: "Logged out" }, { status: 200 });

  // Clear the token cookie using the exact same path it was set with on login (path="/").
  // A second cookies.set() with a different path would overwrite this in Next.js
  // ResponseCookies (Map-keyed by name), leaving the original cookie alive — so we only
  // call this once.
  clearAppSessionCookie(response);

  return response;
}
