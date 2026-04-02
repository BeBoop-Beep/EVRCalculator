import { createSupabaseAdminClient } from "@/lib/supabaseServer";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";

const DEFAULT_DASHBOARD_DATA = {
  commandCenter: {
    totalValue: 18245.87,
    change24hPercent: 0.91,
    change7dPercent: 4.38,
    cardsCount: 428,
    sealedCount: 37,
    wishlistCount: 64,
    lastSyncedAt: "2026-03-31T14:08:00.000Z",
    freshnessLabel: "Fresh",
  },
  performance: {
    periodLabel: "Last 7 days",
    points: [
      { dateLabel: "Mar 24", totalValue: 17120 },
      { dateLabel: "Mar 25", totalValue: 17385 },
      { dateLabel: "Mar 26", totalValue: 17640 },
      { dateLabel: "Mar 27", totalValue: 17530 },
      { dateLabel: "Mar 28", totalValue: 17825 },
      { dateLabel: "Mar 29", totalValue: 18080 },
      { dateLabel: "Mar 30", totalValue: 18170 },
      { dateLabel: "Mar 31", totalValue: 18245 },
    ],
  },
  insights: {
    topMovers: [
      { id: "m1", name: "Charizard ex SIR", changePercent7d: 8.7, dollarImpact: 51 },
      { id: "m2", name: "Mew ex Gold", changePercent7d: 6.1, dollarImpact: 13 },
      { id: "m3", name: "Gengar VMAX Alt", changePercent7d: -2.4, dollarImpact: -8 },
    ],
    allocationSummary: [
      { id: "a1", label: "Cards", valuePercent: 68, valueLabel: "$12.4k" },
      { id: "a2", label: "Sealed", valuePercent: 24, valueLabel: "$4.4k" },
      { id: "a3", label: "Merchandise", valuePercent: 8, valueLabel: "$1.4k" },
    ],
    concentrationText: "Top 5 assets represent 46% of total portfolio value.",
  },
};

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatCompactCurrency(value) {
  const abs = Math.abs(value);
  if (abs >= 1000) {
    return `$${(value / 1000).toFixed(1)}k`;
  }
  return `$${value.toFixed(0)}`;
}

async function trySelect({ adminClient, table, select, filters = [], orderBy, limit }) {
  let query = adminClient.from(table).select(select);

  for (const filter of filters) {
    query = query.eq(filter.column, filter.value);
  }

  if (orderBy?.column) {
    query = query.order(orderBy.column, { ascending: !!orderBy.ascending });
  }

  if (typeof limit === "number") {
    query = query.limit(limit);
  }

  const { data, error } = await query;
  if (error) {
    return { data: [], error };
  }

  return { data: data || [], error: null };
}

/**
 * Returns dashboard-ready data for /my-portfolio with graceful fallback.
 */
export async function getCurrentUserPortfolioDashboardData() {
  const { user, error: authError, status } = await getAuthenticatedUserFromCookies();
  if (!user?.id) {
    return {
      data: null,
      error: {
        message: authError || "Not authenticated",
        status: status || 401,
      },
    };
  }

  const adminClient = createSupabaseAdminClient();
  const warnings = [];
  const connectedTables = [];

  const snapshotResult = await trySelect({
    adminClient,
    table: "portfolio_daily_snapshots",
    select: "snapshot_date,total_value,change_24h_percent,change_7d_percent,cards_count,sealed_count,wishlist_count,last_synced_at,freshness_label",
    filters: [{ column: "user_id", value: user.id }],
    orderBy: { column: "snapshot_date", ascending: true },
    limit: 30,
  });

  if (!snapshotResult.error && snapshotResult.data.length > 0) {
    connectedTables.push("portfolio_daily_snapshots");
    const points = snapshotResult.data.slice(-7).map((row) => ({
      dateLabel: new Date(row.snapshot_date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      totalValue: toNumber(row.total_value),
    }));

    const latest = snapshotResult.data[snapshotResult.data.length - 1];

    const topMoversResult = await trySelect({
      adminClient,
      table: "portfolio_movers_7d",
      select: "asset_id,asset_name,change_percent_7d,current_value",
      filters: [{ column: "user_id", value: user.id }],
      limit: 20,
    });

    if (!topMoversResult.error && topMoversResult.data.length > 0) {
      connectedTables.push("portfolio_movers_7d");
    } else if (topMoversResult.error) {
      warnings.push(`portfolio_movers_7d unavailable: ${topMoversResult.error.message}`);
    }

    const allocationResult = await trySelect({
      adminClient,
      table: "portfolio_allocations",
      select: "bucket_label,bucket_percent,bucket_value",
      filters: [{ column: "user_id", value: user.id }],
      orderBy: { column: "bucket_percent", ascending: false },
      limit: 5,
    });

    if (!allocationResult.error && allocationResult.data.length > 0) {
      connectedTables.push("portfolio_allocations");
    } else if (allocationResult.error) {
      warnings.push(`portfolio_allocations unavailable: ${allocationResult.error.message}`);
    }

    const concentrationResult = await trySelect({
      adminClient,
      table: "portfolio_concentration",
      select: "top_5_percent,summary_text,updated_at",
      filters: [{ column: "user_id", value: user.id }],
      orderBy: { column: "updated_at", ascending: false },
      limit: 1,
    });

    if (!concentrationResult.error && concentrationResult.data.length > 0) {
      connectedTables.push("portfolio_concentration");
    } else if (concentrationResult.error) {
      warnings.push(`portfolio_concentration unavailable: ${concentrationResult.error.message}`);
    }

    const movers = topMoversResult.data.length
      ? topMoversResult.data
          .map((m) => {
            const currentValue = toNumber(m.current_value);
            const changePercent = toNumber(m.change_percent_7d);
            return {
              id: String(m.asset_id || m.asset_name),
              name: m.asset_name || "Unknown Asset",
              changePercent7d: changePercent,
              dollarImpact: Math.round(currentValue * (changePercent / 100)),
            };
          })
          .sort((a, b) => Math.abs(b.dollarImpact) - Math.abs(a.dollarImpact))
          .slice(0, 3)
      : DEFAULT_DASHBOARD_DATA.insights.topMovers;

    const allocations = allocationResult.data.length
      ? allocationResult.data.map((a, idx) => ({
          id: `alloc-${idx}`,
          label: a.bucket_label || `Bucket ${idx + 1}`,
          valuePercent: Math.max(0, Math.min(100, toNumber(a.bucket_percent))),
          valueLabel: formatCompactCurrency(toNumber(a.bucket_value)),
        }))
      : DEFAULT_DASHBOARD_DATA.insights.allocationSummary;

    const concentration = concentrationResult.data[0]?.summary_text || DEFAULT_DASHBOARD_DATA.insights.concentrationText;

    return {
      data: {
        commandCenter: {
          totalValue: toNumber(latest.total_value, DEFAULT_DASHBOARD_DATA.commandCenter.totalValue),
          change24hPercent: toNumber(latest.change_24h_percent, DEFAULT_DASHBOARD_DATA.commandCenter.change24hPercent),
          change7dPercent: toNumber(latest.change_7d_percent, DEFAULT_DASHBOARD_DATA.commandCenter.change7dPercent),
          cardsCount: toNumber(latest.cards_count, DEFAULT_DASHBOARD_DATA.commandCenter.cardsCount),
          sealedCount: toNumber(latest.sealed_count, DEFAULT_DASHBOARD_DATA.commandCenter.sealedCount),
          wishlistCount: toNumber(latest.wishlist_count, DEFAULT_DASHBOARD_DATA.commandCenter.wishlistCount),
          lastSyncedAt: latest.last_synced_at || DEFAULT_DASHBOARD_DATA.commandCenter.lastSyncedAt,
          freshnessLabel: latest.freshness_label || DEFAULT_DASHBOARD_DATA.commandCenter.freshnessLabel,
        },
        performance: {
          periodLabel: "Last 7 days",
          points: points.length ? points : DEFAULT_DASHBOARD_DATA.performance.points,
        },
        insights: {
          topMovers: movers,
          allocationSummary: allocations,
          concentrationText: concentration,
        },
        meta: {
          connectedTables,
          warnings,
          fallbackUsed: false,
        },
      },
      error: null,
    };
  }

  if (snapshotResult.error) {
    warnings.push(`portfolio_daily_snapshots unavailable: ${snapshotResult.error.message}`);
  }

  return {
    data: {
      ...DEFAULT_DASHBOARD_DATA,
      meta: {
        connectedTables,
        warnings,
        fallbackUsed: true,
      },
    },
    error: null,
  };
}
