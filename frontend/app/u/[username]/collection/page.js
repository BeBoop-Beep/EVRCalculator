import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";
import { buildCollectionStats, getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";

const ALLOWED_SORTS = new Set(["recent", "value-desc", "value-asc", "name-asc", "name-desc"]);
const ALLOWED_VIEWS = new Set(["continuous", "binder"]);
const ALLOWED_TYPES = new Set(["cards", "sealed", "merchandise"]);
const ALLOWED_CONDITIONS = new Set([
  "mint",
  "near-mint",
  "lightly-played",
  "moderately-played",
  "heavily-played",
  "sealed",
]);

function readParamValue(searchParams, key) {
  const raw = searchParams?.[key];
  if (Array.isArray(raw)) {
    return String(raw[0] || "").trim();
  }
  return String(raw || "").trim();
}

export default async function PublicProfileCollectionPage({ params, searchParams }) {
  const pageStartedAt = Date.now();
  const { username } = await params;
  const resolvedSearchParams = (await searchParams) || {};
  const normalizedUsername = username || "";

  let publicCollectionAssets = [];
  let publicCollectionFetchError = null;

  try {
    // Guardrail: collection route should not serially block on a separate public profile fetch.
    publicCollectionAssets = await getPublicCollectionEntries(normalizedUsername);
  } catch (error) {
    publicCollectionFetchError = error;
    console.error("[public-collection-page] collection_fetch_failed", {
      username: normalizedUsername,
      message: error instanceof Error ? error.message : String(error),
      status: error?.status || null,
    });
  }

  const collectionStats = buildCollectionStats(publicCollectionAssets);
  const canRenderPublicCollection = !publicCollectionFetchError;

  console.info("[public-collection-lifecycle] page_props", {
    username: normalizedUsername,
    hasPublicProfile: null,
    profileFetchError: null,
    collectionFetchError: publicCollectionFetchError ? (publicCollectionFetchError.message || String(publicCollectionFetchError)) : null,
    count: publicCollectionAssets.length,
    sampleIds: publicCollectionAssets.map((item) => String(item?.id || "")).filter(Boolean).slice(0, 10),
  });

  const q = readParamValue(resolvedSearchParams, "q");
  const sort = readParamValue(resolvedSearchParams, "sort");
  const view = readParamValue(resolvedSearchParams, "view");
  const type = readParamValue(resolvedSearchParams, "type");
  const condition = readParamValue(resolvedSearchParams, "condition");
  const tcg = readParamValue(resolvedSearchParams, "tcg");

  const localToolState = {
    q,
    sort: ALLOWED_SORTS.has(sort) ? sort : "recent",
    view: ALLOWED_VIEWS.has(view) ? view : "continuous",
    type: ALLOWED_TYPES.has(type) ? type : "",
    condition: ALLOWED_CONDITIONS.has(condition) ? condition : "",
    tcg: tcg || "",
  };

  console.info("[public-collection-lifecycle] page_timing", {
    username: normalizedUsername,
    pageRenderPrepMs: Date.now() - pageStartedAt,
    hasPublicProfile: null,
    collectionCount: publicCollectionAssets.length,
  });

  return (
    <div className="space-y-6">
      {!canRenderPublicCollection ? (
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is unavailable</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            This collector has not shared enough public data yet. The public root is reserved for profile-safe collection, showcase, and insight surfaces.
          </p>
        </section>
      ) : (
        <PublicCollectionViewWrapper
          items={publicCollectionAssets}
          stats={collectionStats}
          username={normalizedUsername}
          showPerformanceCard={false}
          localNavToolState={localToolState}
          localNavControlsActive
          serverPreparedAt={Date.now()}
        />
      )}
    </div>
  );
}