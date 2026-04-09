import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";
import { buildCollectionStats, getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";
import { getCachedPublicProfileByUsername } from "@/lib/profile/publicProfileServer";

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
  const { username } = await params;
  const resolvedSearchParams = (await searchParams) || {};
  const normalizedUsername = username || "";

  let publicProfile = null;
  let publicProfileFetchError = null;
  let publicCollectionAssets = [];
  let publicCollectionFetchError = null;

  try {
    publicProfile = await getCachedPublicProfileByUsername(normalizedUsername);
  } catch (error) {
    publicProfileFetchError = error;
    console.error("[public-collection-page] profile_fetch_failed", {
      username: normalizedUsername,
      message: error instanceof Error ? error.message : String(error),
      status: error?.status || null,
      code: error?.code || null,
    });
  }

  if (!publicProfileFetchError && publicProfile) {
    try {
      publicCollectionAssets = await getPublicCollectionEntries(normalizedUsername);
    } catch (error) {
      publicCollectionFetchError = error;
      console.error("[public-collection-page] collection_fetch_failed", {
        username: normalizedUsername,
        message: error instanceof Error ? error.message : String(error),
        status: error?.status || null,
      });
    }
  }

  const collectionStats = buildCollectionStats(publicCollectionAssets);
  const canRenderPublicCollection = Boolean(publicProfile);

  console.info("[public-collection-lifecycle] page_props", {
    username: normalizedUsername,
    hasPublicProfile: Boolean(publicProfile),
    profileFetchError: publicProfileFetchError ? (publicProfileFetchError.message || String(publicProfileFetchError)) : null,
    collectionFetchError: publicCollectionFetchError ? (publicCollectionFetchError.message || String(publicCollectionFetchError)) : null,
    count: publicCollectionAssets.length,
    ids: publicCollectionAssets.map((item) => String(item?.id || "")).filter(Boolean),
    itemMeta: publicCollectionAssets.map((item) => ({
      id: String(item?.id || ""),
      type: String(item?.collectible_type || ""),
      name: String(item?.name || ""),
    })),
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

  return (
    <div className="space-y-6">
      {publicProfileFetchError ? (
        <section className="dashboard-panel rounded-2xl border border-red-500/30 bg-red-500/10 p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public profile failed to load</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Upstream profile fetch failed. This is not treated as an empty/unavailable profile.
          </p>
        </section>
      ) : !canRenderPublicCollection ? (
        <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is unavailable</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            This collector has not shared enough public data yet. The public root is reserved for profile-safe collection, showcase, and insight surfaces.
          </p>
        </section>
      ) : publicCollectionFetchError ? (
        <section className="dashboard-panel rounded-2xl border border-red-500/30 bg-red-500/10 p-5 sm:p-6">
          <p className="text-base font-semibold text-[var(--text-primary)]">Public collection failed to load</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Collection fetch failed upstream and is surfaced explicitly instead of being shown as empty.
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
        />
      )}
    </div>
  );
}