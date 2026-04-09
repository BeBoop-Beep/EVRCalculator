import { cookies } from "next/headers";

const API_URL = process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000";

export async function getAuthenticatedUserFromCookies() {
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  if (!token) {
    return { user: null, error: "Not authenticated", status: 401 };
  }

  try {
    const response = await fetch(`${API_URL}/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.user) {
      return {
        user: null,
        error: data?.message || "Invalid or expired token",
        status: response.status || 401,
      };
    }

    return { user: data.user, error: null, status: 200 };
  } catch (error) {
    return { user: null, error: "Auth service unavailable", status: 500 };
  }
}
