import MyCollectionOverviewDashboardClient from "@/components/Profile/MyCollectionOverviewDashboardClient";
import MyCollectionPortfolioTasks from "@/components/Profile/MyCollectionPortfolioTasks";
import MyCollectionOperationalIntelligence from "@/components/Profile/MyCollectionOperationalIntelligence";
import { getCurrentUserPortfolioDashboardData } from "@/lib/profile/portfolioDashboardQueries";

export default async function MyCollectionOverviewPage() {
  // Guardrail: owner overview must stay on dashboard snapshot data and avoid include_collection_items=1.
  const dashboardResult = await getCurrentUserPortfolioDashboardData();
  const dashboardData = dashboardResult.error ? null : (dashboardResult.data || null);

  return (
    <section className="space-y-6">
      <MyCollectionOverviewDashboardClient dashboardData={dashboardData} />
      <MyCollectionOperationalIntelligence />
      <MyCollectionPortfolioTasks collectionItems={[]} />
    </section>
  );
}
