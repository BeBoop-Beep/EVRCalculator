'use client';
import SecondaryNav from "@/components/SecondaryNav";

export default function AnalyticsPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl md:text-4xl font-bold text-primary mb-4">
            Pokémon TCG Analytics
          </h1>
          <p className="text-lg text-neutral-dark mb-8">
            Analyze market trends and collection insights.
          </p>

          <div className="bg-white rounded-lg shadow-md p-8">
            <div className="text-center text-neutral-dark">
              <p className="mb-4">Analytics dashboard coming soon...</p>
              <p className="text-sm">This page will display detailed analytics, trends, and market insights for Pokémon TCG cards.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
