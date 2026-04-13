import { NextResponse } from "next/server";

export async function POST() {
  const response = NextResponse.json({ message: "Logged out" }, { status: 200 });

  // Clear the token cookie using the exact same path it was set with on login (path="/").
  // A second cookies.set() with a different path would overwrite this in Next.js
  // ResponseCookies (Map-keyed by name), leaving the original cookie alive — so we only
  // call this once.
  response.cookies.set("token", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    expires: new Date(0),
    maxAge: 0,
    path: "/",
    sameSite: "strict",
  });

  return response;
}
