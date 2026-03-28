import { NextResponse } from "next/server"; 
import { serialize } from "cookie";

export async function POST() {
  // Create the first cookie with the path set to '/'
  const cookie1 = serialize("token", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    expires: new Date(0), // Expire the cookie immediately
    path: "/", // Accessible on the root path
    sameSite: "Strict",
  });

  // Create the second cookie with the path set to '/api'
  const cookie2 = serialize("token", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    expires: new Date(0), // Expire the cookie immediately
    path: "/api", // Accessible on the '/api' path
    sameSite: "Strict",
  });

  return NextResponse.json(
    { message: "Logged out" },
    { status: 200, headers: { "Set-Cookie": [cookie1, cookie2] } }
  );
}
