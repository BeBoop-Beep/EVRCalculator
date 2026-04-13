/** @typedef {import("@/types/profile").ProfileResponse} ProfileResponse */
/** @typedef {import("@/types/profile").TcgOption} TcgOption */
/** @typedef {import("@/types/profile").ProfileUpdatePayload} ProfileUpdatePayload */

async function parseJsonResponse(response) {
  let payload = null;

  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.error || "Request failed";
    const requestError = new Error(message);
    requestError.status = response.status;
    throw requestError;
  }

  return payload;
}

/** @returns {Promise<ProfileResponse>} */
export async function getCurrentAuthenticatedUserProfile() {
  const response = await fetch("/api/profile", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });

  return parseJsonResponse(response);
}

// Backward-compatible alias for existing page usage.
export const getCurrentUserProfile = getCurrentAuthenticatedUserProfile;

/** @returns {Promise<{tcgs: TcgOption[]}>} */
export async function getTcgOptions() {
  const response = await fetch("/api/tcgs", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });

  return parseJsonResponse(response);
}

/** @param {ProfileUpdatePayload} payload */
/** @returns {Promise<ProfileResponse>} */
export async function updateCurrentUserProfile(payload) {
  const response = await fetch("/api/profile", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseJsonResponse(response);
}

export async function logoutCurrentUser() {
  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "include",
  });

  return parseJsonResponse(response);
}


