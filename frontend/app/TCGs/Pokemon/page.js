'use client';
import SecondaryNav from "@/components/SecondaryNav";

export default function PokemonPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl md:text-4xl font-bold text-primary mb-4">
            Pokémon Trading Card Game
          </h1>
          <p className="text-lg text-neutral-dark mb-8">
            Explore, analyze, and discover Pokémon TCG cards and sets.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-200">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Overview
              </h2>
              <p className="text-neutral-dark">
                Get a comprehensive overview of Pokémon TCG data, trends, and statistics.
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-200">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Sets
              </h2>
              <p className="text-neutral-dark">
                Browse and explore all available Pokémon TCG sets with detailed information.
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-200">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Analytics
              </h2>
              <p className="text-neutral-dark">
                Analyze market trends, card prices, and collection insights.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
