import { NextResponse } from "next/server";
import { createSupabaseAnonClient } from "@/lib/supabaseServer";

export async function POST(req) {
  const { email } = await req.json();
  const normalizedEmail = typeof email === "string" ? email.trim().toLowerCase() : "";

  if (!normalizedEmail) {
    return NextResponse.json({ message: "Email is required." }, { status: 400 });
  }

  try {
    const anonClient = createSupabaseAnonClient();
    const { error } = await anonClient.auth.resend({
      type: "signup",
      email: normalizedEmail,
    });

    if (error) {
      return NextResponse.json(
        { message: error.message || "Unable to resend confirmation email." },
        { status: 400 }
      );
    }

    return NextResponse.json(
      { message: "Confirmation email sent. Please check your inbox and spam folder." },
      { status: 200 }
    );
  } catch (error) {
    return NextResponse.json(
      { message: "Server error while resending confirmation email." },
      { status: 500 }
    );
  }
}
