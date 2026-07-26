import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";

// Internal cache-invalidation endpoint for Pokemon set snapshots.
//
// After a successful snapshot publication the backend (or an operator) POSTs
// here so the Next.js data-cache tags that seed the set-detail page are
// invalidated immediately, instead of serving a cached response up to
// SHELL/OVERVIEW_SNAPSHOT_REVALIDATE_S stale. This is the "invalidate" half of
// the publication-freshness contract: a newer published source must not be
// shadowed by an older cached response (see pokemonSetInitialSnapshotsServer.js
// tags `pokemon-set-shell:<setId>` and `pokemon-set-overview:<setId>:<window>`).
//
// Guarded by SET_REVALIDATION_SECRET so only the publisher can trigger it.

export const dynamic = "force-dynamic";

const OVERVIEW_WINDOWS = ["365d", "180d", "90d", "30d", "7d"];

function isAuthorized(request) {
  const expected = String(process.env.SET_REVALIDATION_SECRET || "").trim();
  if (!expected) {
    // Unconfigured: refuse rather than allow anonymous cache busting.
    return false;
  }
  const provided = String(request.headers.get("x-revalidate-secret") || "").trim();
  return provided.length > 0 && provided === expected;
}

export async function POST(request) {
  if (!isAuthorized(request)) {
    return NextResponse.json(
      { ok: false, code: "UNAUTHORIZED", message: "Missing or invalid revalidation secret" },
      { status: 401 }
    );
  }

  let body = {};
  try {
    body = (await request.json()) || {};
  } catch {
    body = {};
  }

  const setId = String(body?.setId || "").trim();
  if (!setId) {
    return NextResponse.json(
      { ok: false, code: "SET_ID_REQUIRED", message: "setId is required" },
      { status: 400 }
    );
  }

  const requestedWindows = Array.isArray(body?.windows) && body.windows.length > 0
    ? body.windows.map((value) => String(value || "").trim()).filter(Boolean)
    : OVERVIEW_WINDOWS;

  const invalidated = [];
  const shellTag = `pokemon-set-shell:${setId}`;
  revalidateTag(shellTag);
  invalidated.push(shellTag);
  for (const window of requestedWindows) {
    const overviewTag = `pokemon-set-overview:${setId}:${window}`;
    revalidateTag(overviewTag);
    invalidated.push(overviewTag);
  }

  return NextResponse.json({ ok: true, setId, invalidated });
}
