import { NextResponse } from "next/server";
import { createSupabaseAnonClient } from "@/lib/supabaseServer";

export async function POST() {
  try {
    // Best-effort auth cleanup on Supabase side.
    const anonClient = createSupabaseAnonClient();
    await anonClient.auth.signOut();
  } catch (error) {
    // Continue local logout even if remote sign-out is unavailable.
  }

  const response = NextResponse.json({ message: "Logged out" }, { status: 200 });

  response.cookies.set("token", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    expires: new Date(0),
    path: "/",
    sameSite: "strict",
  });

  response.cookies.set("token", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    expires: new Date(0),
    path: "/api",
    sameSite: "strict",
  });

  return response;
}
