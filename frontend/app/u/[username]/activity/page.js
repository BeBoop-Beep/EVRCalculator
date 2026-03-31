import RoutePageShell from "@/components/Profile/RoutePageShell";
import PublicActivityTimeline from "@/components/Profile/PublicActivityTimeline";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

// Mock data generator for activity
function generateMockActivityItems(username) {
  const seed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const activities = [
    {
      type: "added",
      title: "Added card to collection",
      description: "A new Charizard VMAX was added to the collection.",
      cardName: "Charizard VMAX Ultimate Master",
    },
    {
      type: "graded",
      title: "Card graded successfully",
      description: "Received PSA 9 grade for Blastoise EX holographic.",
      cardName: "Blastoise EX",
    },
    {
      type: "featured",
      title: "Promoted to featured showcase",
      description: "Mewtwo VMAX was added to favorite items showcase.",
      cardName: "Mewtwo VMAX",
    },
    {
      type: "wishlist",
      title: "Added to wishlist",
      description: "Base Set Venusaur was added to high priority wishlist.",
      cardName: "Venusaur (Base Set)",
    },
    {
      type: "valued",
      title: "Collection valued",
      description: "Portfolio received updated valuation from market data.",
      cardName: "Full Collection",
    },
    {
      type: "sold",
      title: "Removed from collection",
      description: "Duplicate card was removed from active collection.",
      cardName: "Pikachu V",
    },
  ];

  const daysAgo = ["Today", "Yesterday", "2 days ago", "5 days ago", "1 week ago", "2 weeks ago"];

  const items = [];
  for (let i = 0; i < 12; i++) {
    const actIdx = (seed + i) % activities.length;
    const dayIdx = i % daysAgo.length;

    items.push({
      id: `activity-${i}`,
      ...activities[actIdx],
      timestampLabel: daysAgo[dayIdx],
      details: [
        { label: "Item", value: activities[actIdx].cardName },
        { label: "Status", value: ["Added", "Graded", "Showcased", "Tracked", "Valued", "Archived"][i % 6] },
      ],
    });
  }

  return items;
}

export default async function PublicActivityPage({ params }) {
  const { username } = await params;
  const { identity } = await getCachedPublicRouteContextByUsername(username || "");
  const ownerLabel = identity.displayName || identity.username;

  // Generate mock activity items
  const activityItems = generateMockActivityItems(username);

  return (
    <RoutePageShell
      eyebrow="Public Activity"
      title={`${ownerLabel}'s Activity`}
      subtitle="Timeline of collector actions and updates shared publicly."
    >
      <div className="space-y-6">
        {/* Activity Filter Info */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            This activity feed shows public updates from the collector's portfolio. Only actions marked as public are displayed.
          </p>
        </div>

        {/* Activity Timeline */}
        <PublicActivityTimeline
          activities={activityItems}
          emptyMessage="This collector hasn't shared any public activity yet."
        />

        {/* Activity Stats */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ActivityStatCard
            label="Total Activities"
            value={activityItems.length}
            icon="📊"
          />
          <ActivityStatCard
            label="This Month"
            value={Math.floor(activityItems.length * 0.4)}
            icon="📅"
          />
          <ActivityStatCard
            label="Cards Added"
            value={Math.floor(activityItems.length * 0.3)}
            icon="➕"
          />
          <ActivityStatCard
            label="Grades Received"
            value={Math.floor(activityItems.length * 0.2)}
            icon="🏆"
          />
        </div>

        {/* Activity Info */}
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4">
          <h3 className="font-semibold text-[var(--text-primary)]">Activity Insights</h3>
          <ul className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
            <li>• Most active on weekends</li>
            <li>• Prefers high-grade cards</li>
            <li>• Recently focused on Base Set acquisitions</li>
          </ul>
        </div>
      </div>
    </RoutePageShell>
  );
}

function ActivityStatCard({ label, value, icon }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 text-center">
      <p className="text-2xl">{icon}</p>
      <p className="mt-2 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
