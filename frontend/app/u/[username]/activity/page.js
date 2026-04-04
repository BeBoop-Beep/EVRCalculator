import PublicActivityTimeline from "@/components/Profile/PublicActivityTimeline";

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

  // Generate mock activity items
  const activityItems = generateMockActivityItems(username);

  return (
    <div className="space-y-6">
        {/* Activity Filter Info */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            This activity feed shows public updates from the collector&apos;s portfolio. Only actions marked as public are displayed.
          </p>
        </div>

        {/* Activity Timeline */}
        <PublicActivityTimeline
          activities={activityItems}
          emptyMessage="This collector hasn&apos;t shared any public activity yet."
        />
    </div>
  );
}
