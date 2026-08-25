export function normalizeOverallProductRankings(payload) {
  if (!payload || payload.available !== true || !Array.isArray(payload.rows)) {
    return { status: "unavailable", reason: payload?.reason || "backend_error", data: null };
  }
  return { status: "available", reason: null, data: payload };
}
