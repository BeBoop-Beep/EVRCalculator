import MyCollectionOverviewDashboardClient from "@/components/Profile/MyCollectionOverviewDashboardClient";
import MyCollectionOperationalIntelligence from "@/components/Profile/MyCollectionOperationalIntelligence";

export default function MyCollectionOverviewPage() {
  return (
    <section className="space-y-6">
      <MyCollectionOverviewDashboardClient />
      <MyCollectionOperationalIntelligence />
    </section>
  );
}
