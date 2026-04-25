function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildBackendUrl(path, searchParams = null) {
  const baseUrl = getBackendBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${baseUrl}${normalizedPath}`);

  if (searchParams) {
    searchParams.forEach((value, key) => {
      url.searchParams.append(key, value);
    });
  }

  return url;
}

export async function getLatestEvrRunSnapshot({ targetType, targetId }) {
  const params = new URLSearchParams();
  params.set("target_type", String(targetType || ""));
  params.set("target_id", String(targetId || ""));

  const response = await fetch(buildBackendUrl("/evr/runs/latest", params).toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    return {
      data: null,
      error: {
        message: payload?.detail || payload?.message || `Request failed (${response.status})`,
        status: response.status,
      },
    };
  }

  return {
    data: payload?.snapshot || null,
    error: null,
  };
}
