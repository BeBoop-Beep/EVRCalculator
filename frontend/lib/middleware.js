import { NextResponse } from "next/server";
import { verify } from "jsonwebtoken";

export async function middleware(req) {
  const token = req.cookies.get("token")?.value;
  console.log("Retrieved token in middleware:", token); 

  // Define protected route prefixes.
  const protectedRoutes = ["/dashboard", "/profile", "/my-portfolio", "/my-collection", "/account-settings"];
  const isProtectedRoute = protectedRoutes.some(
    (route) => req.nextUrl.pathname === route || req.nextUrl.pathname.startsWith(`${route}/`)
  );

  if (isProtectedRoute) {
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
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/my-portfolio/:path*",
    "/my-collection/:path*",
    "/account-settings/:path*",
  ],
};
