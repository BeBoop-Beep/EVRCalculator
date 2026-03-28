// /app/api/auth/login/route.js
import { sign } from "jsonwebtoken";
import Customer from "@/models/Customer"; // Import your customer model for DB queries

export async function POST(req) {
  try {
    const { email, password } = await req.json(); // Get email and password from request body

    // Find customer in the database (replace this with actual DB query)
    const customer = await Customer.findOne({ email });

    if (!customer || customer.password !== password) {
      return new Response(JSON.stringify({ message: "Invalid credentials" }), { status: 401 });
    }

    // Create a JWT token
    const token = sign(
      { id: customer.id, email: customer.email, name: customer.name },
      process.env.JWT_SECRET,
      { expiresIn: "1h" } // You can change the expiration as needed
    );

    return new Response(JSON.stringify({ token }), { status: 200 });

  } catch (error) {
    console.error(error);
    return new Response(JSON.stringify({ message: "Server error" }), { status: 500 });
  }
}
