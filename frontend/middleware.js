import { NextResponse } from "next/server";

/**
 * Edge-compatible middleware. Checks for the presence of the httpOnly `token`
 * cookie and redirects unauthenticated users away from protected routes.
 *
 * Full JWT verification happens in /api/auth/me (Node.js runtime) — this
 * middleware only acts as a fast gate for obviously unauthenticated requests.
 */
export function middleware(req) {
  const token = req.cookies.get("token")?.value;

  const protectedRoutes = [
    "/dashboard",
    "/profile",
    "/my-portfolio",
    "/my-collection",
    "/account-settings",
  ];

  const isProtectedRoute = protectedRoutes.some(
    (route) =>
      req.nextUrl.pathname === route ||
      req.nextUrl.pathname.startsWith(`${route}/`)
  );

  if (isProtectedRoute && !token) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/my-portfolio/:path*",
    "/my-collection/:path*",
    "/account-settings/:path*",
  ],
};
