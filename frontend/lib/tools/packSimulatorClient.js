async function parseJsonResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.detail || payload?.error || "Request failed";
    const requestError = new Error(message);
    requestError.status = response.status;
    requestError.payload = payload;
    throw requestError;
  }

  return payload;
}

export async function runPackSimulation(payload, options = {}) {
  const { signal } = options;
  const response = await fetch("/api/tools/pack-simulator", {
    method: "POST",
    credentials: "include",
    signal,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseJsonResponse(response);
}
