import { NextResponse } from "next/server";

const API_URL = process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000";

export async function POST(req) {
  const { email } = await req.json();
  const normalizedEmail = typeof email === "string" ? email.trim().toLowerCase() : "";

  if (!normalizedEmail) {
    return NextResponse.json({ message: "Email is required." }, { status: 400 });
  }

  try {
    const backendResponse = await fetch(`${API_URL}/auth/resend-confirmation`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email: normalizedEmail,
      }),
    });
    const data = await backendResponse.json().catch(() => ({}));

    if (!backendResponse.ok) {
      return NextResponse.json(
        { message: data?.message || "Unable to resend confirmation email." },
        { status: backendResponse.status || 400 }
      );
    }

    return NextResponse.json(data, { status: backendResponse.status });
  } catch (error) {
    return NextResponse.json(
      { message: "Server error while resending confirmation email." },
      { status: 500 }
    );
  }
}
