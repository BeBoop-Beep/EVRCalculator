import jwt from "jsonwebtoken"; // JWT library
import { NextResponse } from "next/server"; // Import NextResponse
import { createSupabaseAnonClient, createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function POST(req) {
  const { name, email, password } = await req.json(); // Parse the request body

  // Input validation
  if (!name || !email || !password) {
    return NextResponse.json({ error: "Please provide all required fields." }, { status: 400 });
  }

  try {
    const anonClient = createSupabaseAnonClient();
    const adminClient = createSupabaseAdminClient();

    const { data: signUpData, error: signUpError } = await anonClient.auth.signUp({
      email,
      password,
      options: {
        data: { username: name },
      },
    });

    if (signUpError || !signUpData?.user) {
      const isConflict = signUpError?.message?.toLowerCase().includes("already");
      return NextResponse.json(
        { error: signUpError?.message || "Signup failed." },
        { status: isConflict ? 400 : 500 }
      );
    }

    const user = signUpData.user;
    const { error: upsertError } = await adminClient.from("users").upsert(
      {
        id: user.id,
        email,
        username: name,
      },
      { onConflict: "id" }
    );

    if (upsertError) {
      console.error("Error upserting customer profile:", upsertError);
      return NextResponse.json({ error: "Failed to create customer profile." }, { status: 500 });
    }

    const token = jwt.sign(
      { id: user.id, email, name },
      process.env.JWT_SECRET,
      { expiresIn: '1d' }
    );

    const response = NextResponse.json(
      {
        message: 'Signup successful',
        user: {
          id: user.id,
          name,
          email,
        }
      }, 
      { status: 201 }
    );

    response.cookies.set('token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      maxAge: 60 * 60 * 24,
      path: '/',
      sameSite: 'strict',
    });

    return response;
  } catch (error) {
    console.error("Error during signup:", error);
    return NextResponse.json({ error: "Server error. Please try again later." }, { status: 500 });
  }
}
