// /app/api/auth/me/route.js
import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET(req) {
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  // console.log("Token from cookies:", token); 

  if (!token) {
    return NextResponse.json({ message: "Not authenticated" }, { status: 401 });
  }

  try {
    const user = verify(token, process.env.JWT_SECRET);
    return NextResponse.json({ user }, { status: 200 });
  } catch (error) {
    console.error("Invalid token", error);

    if (error.name === "TokenExpiredError") {
      return NextResponse.json({ message: "Token expired" }, { status: 401 });
    }

    return NextResponse.json({ message: "Invalid token" }, { status: 401 });
  }
}
