import MyCollectionOverviewDashboardClient from "@/components/Profile/MyCollectionOverviewDashboardClient";
import MyCollectionPortfolioTasks from "@/components/Profile/MyCollectionPortfolioTasks";
import MyCollectionOperationalIntelligence from "@/components/Profile/MyCollectionOperationalIntelligence";
import { getPrivateCollectionEntries } from "@/lib/profile/collectionEntryLoader";

export default async function MyCollectionOverviewPage() {
  const collectionItems = await getPrivateCollectionEntries();

  return (
    <section className="space-y-6">
      <MyCollectionOverviewDashboardClient collectionItems={collectionItems} />
      <MyCollectionOperationalIntelligence />
      <MyCollectionPortfolioTasks collectionItems={collectionItems} />
    </section>
  );
}
