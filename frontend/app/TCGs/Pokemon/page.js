import SecondaryNav from "@/components/SecondaryNav";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getExploreBackground } from "@/lib/explore/exploreBackgrounds.mjs";
import { NOINDEX_FOLLOW_ROBOTS } from "@/lib/seo/routeMetadata.mjs";

// This page renders three static description cards and no real data — the
// content it describes lives on /Rankings, /TCGs/Pokemon/Sets and the set
// pages. It stays as a hub but is not an independent search destination.
//
// `'use client'` was removed so this route can declare metadata: nothing here
// uses state, effects or event handlers. SecondaryNav is still a client
// component and is imported normally.
export const metadata = { robots: NOINDEX_FOLLOW_ROBOTS };

export default function PokemonPage() {
  // Same environment /Market and /Rankings wear: `.index-environment` is the
  // room (wall gradient, side walls, ambient key light, vignette, grain) and
  // `PageArtworkAtmosphere` is the Pokemon wordmark mural, which the
  // `.explore-glass-scope` compound takes to luminance relief exactly as it
  // does on Market. `isolate` keeps the negative-z layers inside this root.
  // No layout, content or component here changes.
  return (
    <div className="min-h-screen bg-[var(--app-background)] explore-glass-scope index-environment relative isolate">
      <PageArtworkAtmosphere
        src={getExploreBackground("pokemon")}
        dataAttribute="data-tcg-ambient-artwork"
        visibilityClassName="hidden desk:block"
        loading="lazy"
      />
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="dashboard-container">
          <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] mb-4">
            Pokémon Trading Card Game
          </h1>
          <p className="text-lg text-[var(--text-secondary)] mb-8">
            Explore, analyze, and discover Pokémon TCG cards and sets.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-6 hover:bg-[var(--surface-hover)] transition-colors duration-200">
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                Overview
              </h2>
              <p className="text-[var(--text-secondary)]">
                Get a comprehensive overview of Pokémon TCG data, trends, and statistics.
              </p>
            </div>

            <div className="bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-6 hover:bg-[var(--surface-hover)] transition-colors duration-200">
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                Sets
              </h2>
              <p className="text-[var(--text-secondary)]">
                Browse and explore all available Pokémon TCG sets with detailed information.
              </p>
            </div>

            <div className="bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-6 hover:bg-[var(--surface-hover)] transition-colors duration-200">
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                Analytics
              </h2>
              <p className="text-[var(--text-secondary)]">
                Analyze market trends, card prices, and collection insights.
              </p>
            </div>
          </div>
            </div>
          </div>
      </main>
    </div>
  );
}
