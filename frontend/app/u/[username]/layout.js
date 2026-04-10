// Presentation layout: consumes precomputed summary data from publicProfileServer; keep display-only logic here.
import PublicProfileHeader from "@/components/Profile/PublicProfileHeader";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

function normalizeSummaryMetricValue(value) {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed === "" ? null : trimmed;
  }

  return value;
}

function formatCurrencyOrUnknown(value) {
  const normalizedValue = normalizeSummaryMetricValue(value);
  if (normalizedValue === null) {
    return "N/A";
  }

  const parsed = Number(normalizedValue);
  if (!Number.isFinite(parsed)) {
    return "N/A";
  }

  return `$${parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCountOrUnknown(value) {
  const normalizedValue = normalizeSummaryMetricValue(value);
  if (normalizedValue === null) {
    return "N/A";
  }

  const parsed = Number(normalizedValue);
  if (!Number.isFinite(parsed)) {
    return "N/A";
  }

  return parsed.toLocaleString("en-US");
}

export default async function PublicProfileLayout({ children, params }) {
  const { username } = await params;
  const { publicProfile, identity } = await getCachedPublicRouteContextByUsername(username || "");
  const summary = publicProfile?.collection_summary || null;

  const collectionMetrics = {
    portfolioValue: formatCurrencyOrUnknown(summary?.portfolio_value),
    portfolioDelta1d: normalizeSummaryMetricValue(summary?.portfolio_delta_1d),
    portfolioDeltaPct1d: normalizeSummaryMetricValue(summary?.portfolio_delta_pct_1d),
    cards: formatCountOrUnknown(summary?.cards_count),
    sealed: formatCountOrUnknown(summary?.sealed_count),
    graded: formatCountOrUnknown(summary?.graded_count),
  };

  if (publicProfile?.collection_summary_warning) {
    console.error(publicProfile.collection_summary_warning);
  }

  const joinDateLabel = publicProfile?.created_at
    ? new Date(publicProfile.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
      })
    : "New collector";
  const publicProfileHeaderProps = {
    identity,
    avatarUrl: publicProfile?.avatar_url || null,
    bio: publicProfile?.bio || "Collector profile details will appear here.",
    favoriteTcg: publicProfile?.favorite_tcg_name || "Favorite TCG not set",
    joinDateLabel,
    visibility:
      publicProfile?.is_profile_public === true
        ? "Public"
        : publicProfile?.is_profile_public === false
          ? "Private"
          : "Visibility TBD",
    collectionMetrics,
  };

  const renderProfileHeader = () => <PublicProfileHeader {...publicProfileHeaderProps} />;

  return (
    <main className="w-full pb-8 pt-4 lg:py-8">
      <div className="px-6 xl:hidden">{renderProfileHeader()}</div>

      <PublicProfileLocalScaffold
        profileBaseHref={identity.profileHref}
        desktopHeader={renderProfileHeader()}
      >
        {children}
      </PublicProfileLocalScaffold>
    </main>
  );
}
