import { appSessionJson, exchangeSupabaseSession } from "@/lib/auth/appSession";
import { NextResponse } from "next/server";

export async function POST(request) {
  try {
    const { accessToken } = await request.json();
    if (typeof accessToken !== "string" || !accessToken) {
      return NextResponse.json({ message: "Authentication session is required." }, { status: 400 });
    }
    return appSessionJson(await exchangeSupabaseSession(accessToken));
  } catch {
    return NextResponse.json({ message: "Authentication service is unavailable." }, { status: 503 });
  }
}
