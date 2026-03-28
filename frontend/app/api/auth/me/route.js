// /app/api/auth/me/route.js
import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";

export async function GET(req) {
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  // console.log("Token from cookies:", token); 

  if (!token) {
    // console.log("No token found in cookies.");
    return new Response(JSON.stringify({ message: "Not authenticated" }), { status: 401 });
  }

  try {
    const user = verify(token, process.env.JWT_SECRET);
    // console.log("Decoded user:", user); 
    return new Response(JSON.stringify({ user }), { status: 200 });
  } catch (error) {
    console.error("Invalid token", error);

    if (error.name === "TokenExpiredError") {
      return new Response(JSON.stringify({ message: "Token expired" }), { status: 401 });
    }

    return new Response(JSON.stringify({ message: "Invalid token" }), { status: 401 });
  }
}
