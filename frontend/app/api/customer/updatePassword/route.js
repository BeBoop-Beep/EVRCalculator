import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import { createSupabaseAnonClient, createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function PUT(req) {
  try {
    const anonClient = createSupabaseAnonClient();
    const adminClient = createSupabaseAdminClient();

    // Step 1: Get token from cookies or headers
    let token;
    const cookieStore = await cookies();
    token = cookieStore.get("token")?.value;

    if (!token) {
      token = req.headers.get("Authorization")?.split(" ")[1]; // Bearer token
    }

    if (!token) {
      return new Response(JSON.stringify({ error: "Not authenticated" }), { status: 401 });
    }

    // Step 2: Verify the token and extract user info
    const user = verify(token, process.env.JWT_SECRET);
    // console.log("Decoded user:", user);

    // Step 3: Parse the request body for currentPassword and newPassword
    const { currentPassword, newPassword } = await req.json();
    if (!currentPassword || !newPassword) {
      return new Response(JSON.stringify({ error: "All fields are required" }), { status: 400 });
    }

    if (!user?.email || !user?.id) {
      return new Response(JSON.stringify({ error: "Invalid token payload" }), { status: 401 });
    }

    // Step 4: Validate current password by attempting sign in
    const { error: signInError } = await anonClient.auth.signInWithPassword({
      email: user.email,
      password: currentPassword,
    });

    if (signInError) {
      return new Response(JSON.stringify({ error: "Current password is incorrect" }), { status: 401 });
    }

    // Step 5: Update password in Supabase Auth
    const { error: updateError } = await adminClient.auth.admin.updateUserById(user.id, {
      password: newPassword,
    });

    if (updateError) {
      console.error("Error updating password:", updateError);
      return new Response(JSON.stringify({ error: "Failed to update password" }), { status: 500 });
    }

    // Step 6: Return success response
    return new Response(JSON.stringify({ message: "Password updated successfully" }), { status: 200 });
  } catch (error) {
    console.error("Error updating password:", error);
    return new Response(JSON.stringify({ error: "Failed to update password" }), { status: 500 });
  }
}
