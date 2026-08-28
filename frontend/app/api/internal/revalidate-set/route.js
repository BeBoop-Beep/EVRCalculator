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
// tags `pokemon-set-shell:<setId>`, `pokemon-set-overview:<setId>:<window>`,
// and `pokemon-set-market-bootstrap:<setId>:<window>`).
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
  const failed = [];
  const invalidate = (tag) => {
    try {
      revalidateTag(tag);
      invalidated.push(tag);
    } catch (error) {
      // One failing tag must not abandon the rest of the family: a partially
      // invalidated set is still better than a wholly cached one, and the
      // caller needs to know exactly which tags did not clear.
      failed.push({ tag, message: String(error?.message || error) });
    }
  };

  invalidate(`pokemon-set-shell:${setId}`);
  for (const window of requestedWindows) {
    invalidate(`pokemon-set-overview:${setId}:${window}`);
    invalidate(`pokemon-set-market-bootstrap:${setId}:${window}`);
  }

  // Visible publication diagnostics. The backend logs whether invalidation was
  // configured and attempted; this is the other half — what the frontend
  // actually cleared. Without it, "the row was rebuilt but the page shows the
  // previous market date" has no evidence on either side of the call.
  const revalidatedAt = new Date().toISOString();
  console.info("[revalidate-set] tags cleared", {
    setId,
    requestedWindows,
    invalidatedCount: invalidated.length,
    failedCount: failed.length,
    invalidated,
    ...(failed.length > 0 ? { failed } : {}),
    revalidatedAt,
  });

  return NextResponse.json(
    {
      ok: failed.length === 0,
      setId,
      invalidated,
      failed,
      revalidatedAt,
    },
    { status: failed.length === 0 ? 200 : 500 }
  );
}
