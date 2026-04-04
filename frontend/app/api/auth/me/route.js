// /app/api/auth/me/route.js
import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function GET(req) {
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  if (!token) {
    return NextResponse.json({ message: "Not authenticated" }, { status: 401 });
  }

  try {
    const tokenUser = verify(token, process.env.JWT_SECRET);
    const adminClient = createSupabaseAdminClient();

    const { data: profile } = await adminClient
      .from("users")
      .select("id, username, display_name")
      .eq("id", tokenUser.id)
      .maybeSingle();

    const user = {
      ...tokenUser,
      username: profile?.username ?? tokenUser.username ?? null,
      display_name: profile?.display_name ?? null,
    };

    return NextResponse.json({ user }, { status: 200 });
  } catch (error) {
    console.error("Invalid token", error);

    if (error.name === "TokenExpiredError") {
      return NextResponse.json({ message: "Token expired" }, { status: 401 });
    }

    return NextResponse.json({ message: "Invalid token" }, { status: 401 });
  }
}
