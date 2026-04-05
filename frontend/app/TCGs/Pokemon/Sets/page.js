'use client';
import SecondaryNav from "@/components/SecondaryNav";

export default function SetsPage() {
  return (
    <div className="min-h-screen bg-[var(--surface-page)]">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="dashboard-container">
          <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] mb-4">
            Pokémon TCG Sets
          </h1>
          <p className="text-lg text-[var(--text-secondary)] mb-8">
            Browse all available Pokémon Trading Card Game sets.
          </p>

          <div className="bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-8">
            <div className="text-center text-[var(--text-secondary)]">
              <p className="mb-4">Sets database coming soon...</p>
              <p className="text-sm">This page will display comprehensive information about all Pokémon TCG sets.</p>
            </div>
          </div>
            </div>
          </div>
      </main>
    </div>
  );
}
