import PublicPortfolioOverviewComposer from "@/components/Profile/PublicPortfolioOverviewComposer";
import { getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";
import { mapPublicOverviewToDashboardData } from "@/lib/profile/publicOverviewDashboardAdapter";
import { buildPublicOverviewModel } from "@/lib/profile/publicOverviewModel";
import { getCachedPublicProfileByUsername } from "@/lib/profile/publicProfileServer";

function parseCurrencyValue(value) {
  const numeric = Number(String(value ?? "").replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function parsePercentValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  const numeric = Number(String(value ?? "").replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : null;
}

function getItemQuantity(item) {
  const quantity = Number(item?.quantity);
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1;
}

function getItemMarketValue(item) {
  return parseCurrencyValue(item?.valueLabel ?? item?.estimated_value) * getItemQuantity(item);
}

function getAllocationBucket(item) {
  if (item?.collectible_type === "sealed_product" || item?.productType) {
    return "Sealed";
  }

  if (item?.collectible_type === "merchandise") {
    return "Merchandise";
  }

  if (item?.gradingLabel) {
    return "Slabs";
  }

  return "Cards";
}

function buildPublicPerformanceHighlights(items = []) {
  const candidates = items
    .map((item) => {
      const changePercent = parsePercentValue(
        item?.changePercentActive
        ?? item?.changePercentSelectedRange
        ?? item?.changePercent7d
        ?? item?.changePercent30d
        ?? item?.performanceChangePercent
      );

      if (!Number.isFinite(changePercent)) {
        return null;
      }

      return {
        id: item?.id,
        name: item?.name || "Unknown item",
        changePercent,
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.changePercent - a.changePercent);

  if (candidates.length === 0) {
    return null;
  }

  return {
    bestPerformer: candidates[0],
    worstPerformer: candidates[candidates.length - 1],
  };
}

function buildPublicPortfolioSignals(items = []) {
  const assets = items
    .map((item) => ({
      id: item?.id,
      bucket: getAllocationBucket(item),
      marketValue: getItemMarketValue(item),
    }))
    .filter((asset) => asset.marketValue > 0);

  const totalMarketValue = assets.reduce((sum, asset) => sum + asset.marketValue, 0);
  if (totalMarketValue <= 0) {
    return null;
  }

  const bucketValues = new Map();
  const bucketCounts = new Map();

  assets.forEach((asset) => {
    bucketValues.set(asset.bucket, (bucketValues.get(asset.bucket) || 0) + asset.marketValue);
    bucketCounts.set(asset.bucket, (bucketCounts.get(asset.bucket) || 0) + 1);
  });

  const rawRows = Array.from(bucketValues.entries())
    .map(([label, value]) => ({
      label,
      value,
      rawPercent: (value / totalMarketValue) * 100,
    }))
    .sort((a, b) => b.value - a.value);

  const roundedRows = rawRows.map((row) => ({
    ...row,
    basePercent: Math.floor(row.rawPercent),
    remainder: row.rawPercent - Math.floor(row.rawPercent),
  }));

  let remainderBudget = Math.max(0, 100 - roundedRows.reduce((sum, row) => sum + row.basePercent, 0));
  roundedRows
    .slice()
    .sort((a, b) => b.remainder - a.remainder)
    .forEach((row) => {
      if (remainderBudget <= 0) return;
      row.basePercent += 1;
      remainderBudget -= 1;
    });

  const allocationRows = roundedRows.map((row, index) => ({
    id: `public-allocation-${index}-${row.label.toLowerCase()}`,
    label: row.label,
    percent: row.basePercent,
    count: bucketCounts.get(row.label) || 0,
  }));

  const topThreeValue = assets
    .slice()
    .sort((a, b) => b.marketValue - a.marketValue)
    .slice(0, 3)
    .reduce((sum, asset) => sum + asset.marketValue, 0);

  return {
    allocationRows,
    concentrationPercent: Math.round((topThreeValue / totalMarketValue) * 100),
  };
}

export default async function PublicPerformancePage({ params }) {
  const { username } = await params;
  const normalizedUsername = String(username || "").trim();

  const [publicProfile, publicCollectionAssets] = await Promise.all([
    getCachedPublicProfileByUsername(normalizedUsername),
    getPublicCollectionEntries(normalizedUsername),
  ]);

  if (!publicProfile) {
    return (
      <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:p-6">
        <p className="text-base font-semibold text-[var(--text-primary)]">Public profile is unavailable</p>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          This collector has not shared enough public data yet. Performance stays public-safe and collection-first.
        </p>
      </section>
    );
  }

  const overview = buildPublicOverviewModel({
    publicProfile,
    username: normalizedUsername,
    collectionAssets: publicCollectionAssets,
  });
  const dashboardData = mapPublicOverviewToDashboardData(overview);
  const performanceHighlights = buildPublicPerformanceHighlights(publicCollectionAssets);
  const portfolioSignals = buildPublicPortfolioSignals(publicCollectionAssets);

  return (
    <div className="space-y-4">
      <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-4 py-3 sm:px-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Public Performance</p>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Snapshot of portfolio momentum, allocation, and public-safe performance signals.
        </p>
      </section>

      <PublicPortfolioOverviewComposer
        dashboardData={dashboardData}
        performanceHighlights={performanceHighlights}
        portfolioSignals={portfolioSignals}
      />
    </div>
  );
}
