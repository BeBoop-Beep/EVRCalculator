import { sign } from "jsonwebtoken";
import { NextResponse } from "next/server";
import { createSupabaseAnonClient, createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function POST(req) {
  const { email, password } = await req.json();
  const normalizedEmail = typeof email === "string" ? email.trim().toLowerCase() : "";

  if (!normalizedEmail || !password) {
    return NextResponse.json(
      { message: "Email and password are required." },
      { status: 400 }
    );
  }

  try {
    const anonClient = createSupabaseAnonClient();
    const adminClient = createSupabaseAdminClient();

    const { data: signInData, error: signInError } = await anonClient.auth.signInWithPassword({
      email: normalizedEmail,
      password,
    });

    if (signInError || !signInData?.user) {
      return NextResponse.json(
        { message: signInError?.message || "Invalid email or password." },
        { status: 400 }
      );
    }

    const user = signInData.user;
    const { data: profile, error: profileError } = await adminClient
      .from("users")
      .select("username, email")
      .eq("id", user.id)
      .maybeSingle();

    if (profileError) {
      console.error("Error fetching customer profile:", profileError);
    }

    const userName = profile?.username || user.user_metadata?.username || user.user_metadata?.name || "";

    if (!process.env.JWT_SECRET) {
      return NextResponse.json(
        { message: "Server authentication is not configured." },
        { status: 500 }
      );
    }

    const newToken = sign(
      {
        id: user.id,
        email: user.email,
        name: userName,
      },
      process.env.JWT_SECRET,
      { expiresIn: "1d" }
    );

    const response = NextResponse.json(
      {
        id: user.id,
        name: userName,
        email: user.email,
        token: newToken,
      },
      { status: 200 }
    );

    response.cookies.set("token", newToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      maxAge: 60 * 60 * 24,
      path: "/",
    });

    return response;
  } catch (error) {
    console.error("Error during login:", error);
    return NextResponse.json(
      { message: "Server error. Please try again later." },
      { status: 500 }
    );
  }
}
