import { getExplorePagePayload } from "@/lib/explore/explorePageServer";

const IS_DEV = process.env.NODE_ENV !== "production";

export default async function ExplorePage({ searchParams }) {
  const params = await searchParams;

  const targetType = (params?.target_type || "set").toString();
  const targetId = (params?.target_id || "").toString();
  const limitDistributionBins = params?.limit_distribution_bins
    ? parseInt(params.limit_distribution_bins, 10)
    : 50;
  const limitTopHits = params?.limit_top_hits
    ? parseInt(params.limit_top_hits, 10)
    : 10;

  let exploreData = null;
  let exploreError = null;

  try {
    if (targetId) {
      exploreData = await getExplorePagePayload(targetType, targetId, {
        limitDistributionBins,
        limitTopHits,
      });
    }
  } catch (error) {
    console.error("[explore-page] Error loading explore data:", error);
    exploreError = error?.message || "Failed to load explore page data";
  }

  const hasData = exploreData && typeof exploreData === "object";

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container">
        <h1 className="text-2xl font-semibold">Explore</h1>

        {exploreError && (
          <div className="mt-4 rounded-md bg-red-50 p-4">
            <p className="text-sm text-red-800">{exploreError}</p>
          </div>
        )}

        {!targetId && (
          <div className="mt-4 rounded-md bg-blue-50 p-4">
            <p className="text-sm text-blue-800">
              Select a target to view simulation data. Use query params:{" "}
              <code>?target_type=set&amp;target_id=...</code>
            </p>
          </div>
        )}

        {hasData && exploreData.meta?.timings?.total_backend_ms != null && <p className="mt-3 text-xs text-gray-500">Backend: {Math.round(exploreData.meta.timings.total_backend_ms)}ms</p>}

        {hasData && exploreData.meta?.warnings?.length > 0 && (
          <div className="mt-4 rounded-md bg-yellow-50 p-4">
            <p className="text-sm font-medium text-yellow-800">Warnings</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-yellow-700">
              {exploreData.meta.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {IS_DEV && hasData && (
          <section className="mt-6 rounded-md border border-gray-200 bg-gray-50 p-4">
            <p className="text-sm font-medium text-gray-700">Debug Preview</p>
            <pre className="mt-2 max-h-72 overflow-auto rounded bg-white p-3 text-xs text-gray-700">
              {JSON.stringify(exploreData, null, 2)}
            </pre>
          </section>
        )}
      </div>
    </main>
  );
}
