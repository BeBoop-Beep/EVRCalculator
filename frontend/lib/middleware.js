import { NextResponse } from "next/server";
import { verify } from "jsonwebtoken";

export async function middleware(req) {
  const token = req.cookies.get("token"); // Use get() for cookies in Next.js 13 middleware
  console.log("Retrieved token in middleware:", token); 

  // Define protected routes
  const protectedRoutes = ["/dashboard"];

  if (protectedRoutes.includes(req.nextUrl.pathname)) {
    if (!token) {
      return NextResponse.redirect(new URL("/login", req.url)); // Redirect to login if no token
    }

    try {
      // Verify the token
      verify(token, process.env.JWT_SECRET); // Ensure the token is valid
    } catch (error) {
      return NextResponse.redirect(new URL("/login", req.url)); // Redirect if verification fails
    }
  }

  return NextResponse.next();
}

// Configure middleware to run on specific paths
export const config = {
  matcher: ["/dashboard"], // Add more protected routes here
};
