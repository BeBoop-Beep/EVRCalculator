import PublicWishlistDisplay from "@/components/Profile/PublicWishlistDisplay";

// Mock data generator for wishlist items
function generateMockWishlistItems(username) {
  const seed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const desires = ["Charizard VMAX", "Blastoise EX", "Venusaur GX", "Pikachu V", "Mewtwo VMAX"];
  const priorities = ["high", "medium", "low"];

  const items = [];
  const totalItems = 8 + (seed % 6); // 8-13 items

  for (let i = 0; i < totalItems; i++) {
    const desireIdx = (seed + i) % desires.length;
    const priorityIdx = i % priorities.length;

    items.push({
      id: `wishlist-${i}`,
      name: `${desires[desireIdx]} (${["PSA 8", "PSA 9", "Raw"][i % 3]})`,
      tcg: "Pokemon",
      priority: priorities[priorityIdx],
      estimatedValue: Math.floor(Math.random() * 1000) + 100,
      context: `${["PSA 8", "PSA 9", "Raw"][i % 3]} • Actively seeking`,
      valueLabel: `~$${Math.floor(Math.random() * 600) + 200}`,
      imageUrl: null,
      cardNumber: `${Math.floor(Math.random() * 100) + 1}/102`,
      set: [
        "Base Set",
        "Jungle",
        "Fossil",
        "Expedition",
        "Aquapolis",
      ][i % 5],
    });
  }

  return items;
}

export default async function PublicWishlistPage({ params }) {
  const { username } = await params;

  // Generate mock wishlist items
  const wishlistItems = generateMockWishlistItems(username);

  return (
    <div className="space-y-6">
        {/* Info Panel */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            This wishlist shows items the collector is seeking to add to their portfolio. Items are prioritized to show what they're most actively hunting for.
          </p>
        </div>

        {/* Wishlist Display */}
        <PublicWishlistDisplay
          items={wishlistItems}
          priorityGroups={true}
          emptyMessage="This collector hasn't shared a public wishlist yet."
        />

        {/* Wishlist Tips */}
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4">
          <h3 className="font-semibold text-[var(--text-primary)]">About This Wishlist</h3>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Wishlists help collectors track items they want to acquire. High priority items indicate active searches, while medium and low priorities show longer-term goals.
          </p>
        </div>
    </div>
  );
}
