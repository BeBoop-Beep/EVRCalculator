import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { cardProxyResponse } from "@/lib/rankings/cardProxyResponse";

export async function GET(request) {
  const target = new URL(`${getBackendApiBaseUrl()}/explore/card-collector-appeal`);
  for (const [key, value] of request.nextUrl.searchParams) target.searchParams.append(key, value);
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  return cardProxyResponse(() => fetch(target, { headers, cache: "no-store" }));
}
