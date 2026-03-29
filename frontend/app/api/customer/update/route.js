import { sign, verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function PUT(req) {
  try {
    const adminClient = createSupabaseAdminClient();

    // Extract token from cookie or Authorization header
    const cookieStore = await cookies();
    let token = cookieStore.get("token")?.value || req.headers.get("Authorization")?.split(" ")[1];

    if (!token) {
      return new Response(JSON.stringify({ message: "Not authenticated" }), { status: 401 });
    }

    // Verify token
    let user;
    try {
      user = verify(token, process.env.JWT_SECRET);
    } catch (err) {
      return new Response(JSON.stringify({ message: "Invalid or expired token" }), { status: 401 });
    }

    // Parse the request body
    const { name, email } = await req.json();
    const updateFields = {};

    if (name) updateFields.username = name;
    if (email) updateFields.email = email;

    // Remove undefined or empty fields
    Object.keys(updateFields).forEach((key) => {
      if (!updateFields[key]) delete updateFields[key];
    });

    // Ensure at least one field is provided
    if (Object.keys(updateFields).length === 0) {
      return new Response(JSON.stringify({ message: "No fields provided for update" }), { status: 400 });
    }

    const { data: updatedCustomer, error: updateError } = await adminClient
      .from("users")
      .update(updateFields)
      .eq("id", user.id)
      .select("id, username, email")
      .maybeSingle();

    if (updateError) {
      console.error("Error updating customer profile:", updateError);
      return new Response(JSON.stringify({ message: "Failed to update customer" }), { status: 500 });
    }

    if (!updatedCustomer) {
      return new Response(JSON.stringify({ message: "Customer not found" }), { status: 404 });
    }

    // Generate new JWT with updated info
    const newToken = sign(
      { 
        id: updatedCustomer.id,
        email: updatedCustomer.email, 
        name: updatedCustomer.username,
      },
      process.env.JWT_SECRET,
      { expiresIn: "1d" }
    );
    
    // Set secure cookie attributes
    const response = NextResponse.json(
      {
        id: updatedCustomer.id,
        name: updatedCustomer.username,
        email: updatedCustomer.email,
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
    console.error("Error updating customer:", error);
    return new Response(JSON.stringify({ message: "Failed to update customer", error: error.message }), { status: 500 });
  }
}
