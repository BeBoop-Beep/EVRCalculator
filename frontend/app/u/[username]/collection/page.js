import RoutePageShell from "@/components/Profile/RoutePageShell";
import PublicCollectionGrid from "@/components/Profile/PublicCollectionGrid";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

// Mock data generator - seeded by username for consistency
function generateMockCollectionItems(username, count = 12) {
  const seed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const sets = ["Scarlet & Violet", "Sword & Shield", "Sun & Moon", "X & Y", "Black & White"];
  const cardNames = [
    "Charizard EX",
    "Blastoise GX",
    "Venusaur V",
    "Pikachu VMAX",
    "Mewtwo EX",
    "Alakazam GX",
    "Dragonite V",
    "Gyarados VMAX",
    "Articuno EX",
    "Zapdos V",
    "Moltres GX",
    "Lugia VMAX",
  ];

  const items = [];
  for (let i = 0; i < count; i++) {
    const itemSeed = (seed + i) % sets.length;
    items.push({
      id: `collection-${i}`,
      name: cardNames[i % cardNames.length],
      set: sets[itemSeed],
      cardNumber: `${i + 1}/${Math.floor(Math.random() * 200) + 100}`,
      context: `${sets[itemSeed]} • Holo Rare`,
      valueLabel: `$${Math.floor(Math.random() * 500) + 50}`,
      isFoil: Math.random() > 0.7,
      condition: ["NM", "LP", "MP", "HP"][Math.floor(Math.random() * 4)],
      imageUrl: null,
    });
  }
  return items;
}

export default async function PublicCollectionPage({ params }) {
  const { username } = await params;
  const { identity } = await getCachedPublicRouteContextByUsername(username || "");
  const ownerLabel = identity.displayName || identity.username;

  // Generate mock collection items
  const collectionItems = generateMockCollectionItems(username, 16);

  return (
    <RoutePageShell
      eyebrow="Public Collection"
      title={`${ownerLabel}'s Collection`}
      subtitle="Showcase view of this collector's singles and cards."
    >
      <div className="space-y-6">
        {/* View Mode Info */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            Showing {collectionItems.length} items from the public collection. Items are organized by set and rarity.
          </p>
        </div>

        {/* Collection Grid */}
        <PublicCollectionGrid
          items={collectionItems}
          emptyMessage="This collector hasn't shared any collection items yet."
          variant="detailed"
          viewMode="grid"
        />

        {/* Stats Footer */}
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard
            label="Total Cards"
            value={collectionItems.length}
          />
          <StatCard
            label="Sets Represented"
            value={new Set(collectionItems.map((i) => i.set)).size}
          />
          <StatCard
            label="Collection Value"
            value={`$${collectionItems.reduce((sum, i) => sum + parseInt(i.valueLabel?.replace(/\D/g, "") || 0), 0)}`}
          />
        </div>
      </div>
    </RoutePageShell>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
