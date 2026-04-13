function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildProxyHeaders(request) {
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };

  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    headers.cookie = cookieHeader;
  }

  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.authorization = authorization;
  }

  return headers;
}

export async function PUT(req) {
  try {
    const body = await req.json();
    const proxyResponse = await fetch(`${getBackendBaseUrl()}/customer/update-password`, {
      method: "PUT",
      headers: buildProxyHeaders(req),
      body: JSON.stringify(body),
      credentials: "include",
      cache: "no-store",
    });

    const payloadText = await proxyResponse.text();
    const contentType = proxyResponse.headers.get("content-type") || "application/json";

    return new Response(payloadText, {
      status: proxyResponse.status,
      headers: {
        "content-type": contentType,
      },
    });
  } catch (error) {
    console.error("Error updating password:", error);
    return new Response(JSON.stringify({ error: "Failed to update password" }), { status: 500 });
  }
}
