import SecondaryNav from "@/components/SecondaryNav";

export default function LoadingPokemonSetsPage() {
  return (
    <div className="min-h-screen bg-[var(--surface-page)]">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="dashboard-container">
            <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] mb-3">
              Pokémon TCG Sets
            </h1>
            <p className="text-base md:text-lg text-[var(--text-secondary)] mb-8">
              Browse Pokémon sets by era, newest to oldest.
            </p>
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6 text-[var(--text-secondary)]">
              Loading Pokémon sets...
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
