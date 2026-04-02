import PublicShelfDisplay from "@/components/Profile/PublicShelfDisplay";

// Mock data generator for sealed products
function generateMockShelfItems(username, count = 12) {
  const seed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const productTypes = ["Booster Box", "Booster Bundle", "Elite Trainer Box", "Deck Box", "Tin", "Collection Box"];
  const setsAvailable = [
    "Scarlet & Violet",
    "Sword & Shield",
    "Sun & Moon",
    "Hidden Fates",
    "Vivid Voltage",
    "Champion's Path",
  ];

  const items = [];
  for (let i = 0; i < count; i++) {
    const setIdx = (seed + i) % setsAvailable.length;
    const typeIdx = i % productTypes.length;

    items.push({
      id: `shelf-${i}`,
      name: `${setsAvailable[setIdx]} - ${productTypes[typeIdx]}`,
      productType: productTypes[typeIdx],
      set: setsAvailable[setIdx],
      quantity: Math.floor(Math.random() * 3) + 1,
      valueLabel: `$${Math.floor(Math.random() * 600) + 100}`,
      context: `Sealed • ${setsAvailable[setIdx]}`,
      imageUrl: null,
    });
  }
  return items;
}

export default async function PublicShelfPage({ params }) {
  const { username } = await params;

  // Generate mock shelf items
  const shelfItems = generateMockShelfItems(username, 16);

  return (
    <div className="space-y-6">
        {/* Info Panel */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            This section displays sealed products and booster boxes from the collector's inventory. Items are organized by product type and set.
          </p>
        </div>

        {/* Shelf Display */}
        <PublicShelfDisplay
          items={shelfItems}
          groupByType={true}
          emptyMessage="This collector hasn't shared any sealed products yet."
        />

        {/* Shelf Stats */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total Products"
            value={shelfItems.length}
          />
          <StatCard
            label="Total Quantity"
            value={shelfItems.reduce((sum, i) => sum + (i.quantity || 1), 0)}
          />
          <StatCard
            label="Shelf Value"
            value={`$${shelfItems.reduce((sum, i) => sum + parseInt(i.valueLabel?.replace(/\D/g, "") || 0), 0)}`}
          />
          <StatCard
            label="Sets Represented"
            value={new Set(shelfItems.map((i) => i.set)).size}
          />
        </div>
    </div>
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
