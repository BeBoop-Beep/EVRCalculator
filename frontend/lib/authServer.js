import { verify } from "jsonwebtoken";
import { cookies } from "next/headers";

export async function getAuthenticatedUserFromCookies() {
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  if (!token) {
    return { user: null, error: "Not authenticated", status: 401 };
  }

  try {
    const user = verify(token, process.env.JWT_SECRET);
    return { user, error: null, status: 200 };
  } catch (error) {
    return { user: null, error: "Invalid or expired token", status: 401 };
  }
}
