"use client";

import ProfileSection from "@/components/Profile/ProfileSection";

/**
 * @typedef {Object} FeaturedCard
 * @property {string} id
 * @property {string} name
 * @property {string} imageUrl
 * @property {string} set
 * @property {string} cardNumber
 * @property {number} [value]
 * @property {boolean} [isFoil]
 * @property {string} [condition]
 */

/**
 * PublicProfileFeaturedItems - Displays a carousel or grid of featured cards in the public profile.
 * @param {Object} props
 * @param {FeaturedCard[]} [props.items] - Featured cards to display
 * @param {boolean} [props.isLoading] - Loading state
 * @returns {JSX.Element}
 */
export default function PublicProfileFeaturedItems({ items = [], isLoading = false }) {
  // Mock data for demonstration
  const mockItems = [
    {
      id: "1",
      name: "Charizard ex",
      set: "Scarlet & Violet",
      cardNumber: "123/102",
      value: 450,
      imageUrl: "https://images.pokemontcg.io/sv04pt/1_hires.png",
      isFoil: true,
      condition: "PSA 9",
    },
    {
      id: "2",
      name: "Mewtwo ex",
      set: "Scarlet & Violet",
      cardNumber: "65/102",
      value: 280,
      imageUrl: "https://images.pokemontcg.io/sv04pt/65_hires.png",
      isFoil: true,
      condition: "PSA 8",
    },
    {
      id: "3",
      name: "Pikachu",
      set: "Base Set",
      cardNumber: "58/102",
      value: 320,
      imageUrl: "https://images.pokemontcg.io/base1/58_hires.png",
      condition: "NM",
    },
  ];

  const displayItems = items.length > 0 ? items : mockItems;

  if (isLoading) {
    return (
      <ProfileSection title="Featured Items" subtitle="Collector's showcase highlights">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((idx) => (
            <div key={idx} className="animate-pulse">
              <div className="aspect-video rounded-lg bg-[var(--surface-hover)]" />
            </div>
          ))}
        </div>
      </ProfileSection>
    );
  }

  return (
    <ProfileSection title="Featured Items" subtitle="Collector's showcase highlights">
      {displayItems.length === 0 ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
          <p className="text-sm text-[var(--text-secondary)]">No featured items yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {displayItems.map((item) => (
            <div
              key={item.id}
              className="group relative overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] transition-all hover:border-[rgba(255,255,255,0.12)] hover:shadow-lg"
            >
              {/* Card Image */}
              <div className="relative aspect-video overflow-hidden bg-[var(--surface-hover)]">
                {item.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={item.imageUrl}
                    alt={item.name}
                    className="h-full w-full object-cover transition-transform group-hover:scale-105"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
                    No image
                  </div>
                )}

                {/* Foil Badge */}
                {item.isFoil && (
                  <div className="absolute top-2 right-2 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 px-2 py-1 text-xs font-semibold text-white shadow-lg">
                    Foil
                  </div>
                )}

                {/* Condition Badge */}
                {item.condition && (
                  <div className="absolute bottom-2 left-2 rounded-md bg-black/60 px-2 py-1 text-xs font-medium text-white backdrop-blur-sm">
                    {item.condition}
                  </div>
                )}
              </div>

              {/* Card Info */}
              <div className="p-3">
                <h3 className="font-semibold text-[var(--text-primary)] line-clamp-2">{item.name}</h3>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {item.set} • {item.cardNumber}
                </p>

                {item.value && (
                  <div className="mt-2 pt-2 border-t border-[var(--border-subtle)]">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">${item.value.toLocaleString()}</p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </ProfileSection>
  );
}
