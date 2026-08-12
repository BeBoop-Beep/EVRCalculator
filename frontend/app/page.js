import Footer from "@/components/Footer";
import RankingTheaterHomepage from "@/components/landing/RankingTheaterHomepage";
import styles from "@/components/landing/landing.module.css";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

export const metadata = buildRouteMetadata({
  path: "/",
  title: "inDex — Pokémon TCG Opening Intelligence",
  description: "One million simulated openings, current market prices, and one canonical ranking.",
});

export default async function HomePage() {
  const { openingSpotlightSet, openingBoosterPackImage, openingRankingRows, openingDistribution, marketContext } =
    await getLandingPageData();

  return (
    <div className={styles.page}>
      <RankingTheaterHomepage
        set={openingSpotlightSet}
        rankingRows={openingRankingRows}
        boosterPackImage={openingBoosterPackImage}
        distribution={openingDistribution}
        marketContext={marketContext}
      />
      <Footer />
    </div>
  );
}
