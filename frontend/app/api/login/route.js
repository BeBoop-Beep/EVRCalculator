import { mongooseConnect } from "@/lib/mongoose";
import Customer from "@/models/Customer";
import bcrypt from "bcryptjs";
import { sign } from "jsonwebtoken";
import { NextResponse } from "next/server";

export async function POST(req) {
  const { email, password } = await req.json();

  if (!email || !password) {
    return NextResponse.json(
      { message: "Email and password are required." },
      { status: 400 }
    );
  }

  try {
    // Connect to MongoDB
    await mongooseConnect();

    // Find the customer by email
    const customer = await Customer.findOne({ email });
    if (!customer) {
      return NextResponse.json(
        { message: "Invalid email or password." },
        { status: 400 }
      );
    }

    // Compare the provided password with the stored hashed password
    const isMatch = await bcrypt.compare(password, customer.password);
    if (!isMatch) {
      return NextResponse.json(
        { message: "Invalid email or password." },
        { status: 400 }
      );
    }

    // Create a JWT token with the customer info
    const newToken = sign(
      {
        id: customer._id,
        email: customer.email,
        name: customer.name,
        phone: customer.phone,
        address: customer.address,
      },
      process.env.JWT_SECRET,
      { expiresIn: "1d" }
    );

    // Set the JWT token in the cookie
    const response = new Response(
      JSON.stringify({
        id: customer._id,
        name: customer.name,
        email: customer.email,
        phone: customer.phone,
        address: customer.address,
        token: newToken, // Include the token in the response body
      }),
      {
        status: 200,
        headers: {
          "Set-Cookie": `token=${newToken}; HttpOnly; Secure; SameSite=Strict; Max-Age=86400`, // 1 day expiration
        },
      }
    );

    return response; // Return the response with the token in both the cookie and body
  } catch (error) {
    console.error("Error during login:", error);
    return NextResponse.json(
      { message: "Server error. Please try again later." },
      { status: 500 }
    );
  }
}
