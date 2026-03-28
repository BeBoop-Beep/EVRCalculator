import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import bcrypt from "bcryptjs";
import { mongooseConnect } from "@/lib/mongoose"; // Import mongooseConnect
import Customer from "@/models/Customer";

export async function PUT(req) {
  try {
    // Step 1: Get token from cookies or headers
    let token;
    const cookieStore = cookies();
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

    // Step 4: Establish a database connection using mongooseConnect
    await mongooseConnect();

    // Step 5: Find the customer and check the current password
    const customer = await Customer.findById(user.id);
    if (!customer) {
      return new Response(JSON.stringify({ error: "Customer not found" }), { status: 404 });
    }

    const isCurrentPasswordValid = await bcrypt.compare(currentPassword, customer.password);
    if (!isCurrentPasswordValid) {
      return new Response(JSON.stringify({ error: "Current password is incorrect" }), { status: 401 });
    }

    // Step 6: Hash the new password and update it in the database
    const hashedPassword = await bcrypt.hash(newPassword, 10);
    customer.password = hashedPassword;
    await customer.save();

    // Step 7: Return success response
    return new Response(JSON.stringify({ message: "Password updated successfully" }), { status: 200 });
  } catch (error) {
    console.error("Error updating password:", error);
    return new Response(JSON.stringify({ error: "Failed to update password" }), { status: 500 });
  }
}
