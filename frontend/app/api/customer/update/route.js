import { sign, verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import { mongooseConnect } from "@/lib/mongoose";
import Customer from "@/models/Customer";

export async function PUT(req) {
  try {
    await mongooseConnect();

    // Extract token from cookie or Authorization header
    const cookieStore = cookies();
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
    const { name, email, phone, address } = await req.json();
    const updateFields = { name, email, phone, address };

    // Remove undefined or empty fields
    Object.keys(updateFields).forEach((key) => {
      if (!updateFields[key]) delete updateFields[key];
    });

    // Ensure at least one field is provided
    if (Object.keys(updateFields).length === 0) {
      return new Response(JSON.stringify({ message: "No fields provided for update" }), { status: 400 });
    }

    // Update the customer in the database
    const updatedCustomer = await Customer.findByIdAndUpdate(
      user.id,
      updateFields,
      { new: true }
    );

    if (!updatedCustomer) {
      return new Response(JSON.stringify({ message: "Customer not found" }), { status: 404 });
    }

    // Generate new JWT with updated info
    const newToken = sign(
      { 
        id: updatedCustomer._id, 
        email: updatedCustomer.email, 
        name: updatedCustomer.name,
        phone: updatedCustomer.phone, 
        address: updatedCustomer.address 
      },
      process.env.JWT_SECRET,
      { expiresIn: "1d" }
    );
    
    // Set secure cookie attributes
    const response = new Response(
      JSON.stringify({
        id: updatedCustomer._id,
        name: updatedCustomer.name,
        email: updatedCustomer.email,
        phone: updatedCustomer.phone,  // Ensure phone is included
        address: updatedCustomer.address // Ensure address is included
      }),
      { status: 200 }
    );

    response.headers.set(
      "Set-Cookie",
      `token=${newToken}; path=/; max-age=86400; HttpOnly; SameSite=Lax; Secure`
    );

    return response;
  } catch (error) {
    console.error("Error updating customer:", error);
    return new Response(JSON.stringify({ message: "Failed to update customer", error: error.message }), { status: 500 });
  }
}
