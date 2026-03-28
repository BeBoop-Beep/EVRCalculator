import { mongooseConnect } from "@/lib/mongoose"; 
import { serialize } from 'cookie';
import Customer from "@/models/Customer"; // Your customer model
import bcrypt from "bcryptjs"; // Password hashing
import jwt from "jsonwebtoken"; // JWT library
import { NextResponse } from "next/server"; // Import NextResponse

export async function POST(req) {
  const { name, email, password } = await req.json(); // Parse the request body

  // Input validation
  if (!name || !email || !password) {
    return NextResponse.json({ error: "Please provide all required fields." }, { status: 400 });
  }

  try {
    // Connect to MongoDB
    await mongooseConnect();

    // Check if the email already exists
    const existingCustomer = await Customer.findOne({ email });
    if (existingCustomer) {
      return NextResponse.json({ error: "Email already in use." }, { status: 400 });
    }

    // Hash the password
    const hashedPassword = await bcrypt.hash(password, 12);
    // console.log("Hashed password:", hashedPassword);


    // Create a new customer
    const newCustomer = new Customer({
      name,
      email,
      password: hashedPassword,
    });

    // Save customer to the database
    await newCustomer.save();

    // Create a JWT token
    const token = jwt.sign(
      { id: newCustomer._id, email: newCustomer.email, name: newCustomer.name },
      process.env.JWT_SECRET,
      { expiresIn: '1d' }
    );

    // Set the token in a cookie
    const cookie = serialize('token', token, {
      httpOnly: true, // Prevents access to the cookie from JavaScript
      secure: process.env.NODE_ENV === 'production', // Only set the cookie over HTTPS in production
      maxAge: 60 * 60 * 24, // Expires after 1 day
      path: '/', // Cookie is available throughout the site
      sameSite: 'Strict', // Enforces same-site policy
    });
    
    // Attach the cookie to the response
    return NextResponse.json(
      {
        message: 'Signup successful',
        user: {
          name: newCustomer.name,
          email: newCustomer.email,
        }
      }, 
      {
        status: 201,
        headers: {
          'Set-Cookie': cookie,
        },
      }
    );
  } catch (error) {
    console.error("Error during signup:", error);
    return NextResponse.json({ error: "Server error. Please try again later." }, { status: 500 });
  }
}
