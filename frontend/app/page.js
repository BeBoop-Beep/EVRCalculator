import Footer from "@/components/Footer";
import RankingTheaterHomepage from "@/components/landing/RankingTheaterHomepage";
import styles from "@/components/landing/landing.module.css";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { buildSiteStructuredData } from "@/lib/seo/structuredData.mjs";

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
      {/*
        The site's ONE schema.org entity graph (WebSite + Organization), emitted
        here because the homepage is the document those entities describe — see
        lib/seo/structuredData.mjs for why it is not in the root layout and why
        it carries no sameAs. This is a server component, so the script is in
        the HTML Google receives without any client execution.
      */}
      <script
        type="application/ld+json"
        // The payload is a locally-built object of static strings, never user
        // or backend input, so there is no injected content to escape.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(buildSiteStructuredData()) }}
      />
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
