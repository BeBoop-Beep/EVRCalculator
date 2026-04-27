import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";
import { buildCollectionStats, mapPublicCollectionItemsToView } from "@/lib/profile/collectionEntryLoader";
import { getPublicProfilePagePayload } from "@/lib/profile/publicProfileServer";

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

  let payload = null;
  let publicFetchError = null;
  try {
    payload = await getPublicProfilePagePayload(normalizedUsername);
  } catch (error) {
    publicFetchError = error;
    console.error("[public-collection-page] payloadFetchError", {
      username: normalizedUsername,
      message: error instanceof Error ? error.message : String(error),
      status: error?.status || null,
    });
  }

  const hasPublicProfile = Boolean(payload?.profile?.id);
  const warnings = Array.isArray(payload?.meta?.warnings) ? payload.meta.warnings : [];
  const publicCollectionAssets = mapPublicCollectionItemsToView(payload?.collection_items || []);
  const collectionStats = buildCollectionStats(publicCollectionAssets);
  const canRenderPublicCollection = !publicFetchError && hasPublicProfile;

  console.info("[public-collection-lifecycle] page_props", {
    username: normalizedUsername,
    hasPublicProfile,
    payloadFetchError: publicFetchError ? (publicFetchError.message || String(publicFetchError)) : null,
    warnings,
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
    hasPublicProfile,
    collectionCount: publicCollectionAssets.length,
    itemsSource: payload?.meta?.items_source || null,
    timings: payload?.meta?.timings || null,
  });

  return (
    <div className="space-y-6">
      {!canRenderPublicCollection ? (
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
          {Number(publicFetchError?.status || 0) === 500 ? (
            <>
              <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is temporarily unavailable</p>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                We could not load this public profile right now. Please try again shortly.
              </p>
            </>
          ) : (
            <>
              <p className="text-base font-semibold text-[var(--text-primary)]">Profile not found</p>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                The profile you are looking for does not exist or is private.
              </p>
            </>
          )}
        </section>
      ) : (
        <>
          {warnings.length > 0 ? (
            <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4 sm:p-5">
              <p className="text-sm font-semibold text-[var(--text-primary)]">Some public data is partially available</p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">{warnings.join("; ")}</p>
            </section>
          ) : null}

          <PublicCollectionViewWrapper
            items={publicCollectionAssets}
            stats={collectionStats}
            username={normalizedUsername}
            showPerformanceCard={false}
            localNavToolState={localToolState}
            localNavControlsActive
            serverPreparedAt={Date.now()}
          />
        </>
      )}
    </div>
  );
}