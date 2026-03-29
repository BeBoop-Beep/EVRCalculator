'use client';
import SecondaryNav from "@/components/SecondaryNav";

export default function SetsPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl md:text-4xl font-bold text-primary mb-4">
            Pokémon TCG Sets
          </h1>
          <p className="text-lg text-neutral-dark mb-8">
            Browse all available Pokémon Trading Card Game sets.
          </p>

          <div className="bg-white rounded-lg shadow-md p-8">
            <div className="text-center text-neutral-dark">
              <p className="mb-4">Sets database coming soon...</p>
              <p className="text-sm">This page will display comprehensive information about all Pokémon TCG sets.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
