import LandingHero from "@/components/landing/LandingHero";
import MarketStrip from "@/components/landing/MarketStrip";
import LevelsSection from "@/components/landing/LevelsSection";
import SetIntelligenceSection from "@/components/landing/SetIntelligenceSection";
import ExploreSection from "@/components/landing/ExploreSection";
import MethodologySection from "@/components/landing/MethodologySection";
import FinalCtaSection from "@/components/landing/FinalCtaSection";
import Footer from "@/components/Footer";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import styles from "@/components/landing/landing.module.css";

export const metadata = {
  title: "inDex — Pokémon TCG Market Intelligence",
  description:
    "Live Pokémon set values, opening simulations, chase-card movement, and cross-set rankings. Know what's worth opening before you rip.",
};

/**
 * The public homepage.
 *
 * ONE ranked payload drives the whole page (the cached RIP Statistics targets
 * contract Explore reads), plus published Pokemon product content for the two
 * sets the page features — chase cards and sealed pricing, read from the same
 * set-detail endpoints the Overview tab uses. Every section below is a server
 * component holding no state; the only client JavaScript on this route is the
 * waitlist dialog and the card-image error fallback.
 *
 * The bottom of the page clears the fixed mobile navigation through the root
 * layout's `pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0` on <main>,
 * which is why nothing here adds its own bottom-nav offset.
 */
export default async function HomePage() {
  const {
    openingSpotlightSet,
    openingChaseCards,
    openingSealedProducts,
    openingCardsAsOf,
    setIntelligenceSpotlightSet,
    setIntelligenceChaseCards,
    marketSignals,
    bestSetsRows,
    openingRankingRows,
    setValueRankingRows,
    marketContext,
  } = await getLandingPageData();

  return (
    <div className={styles.page}>
      {/* ROLE 1 — current published opening rank #1. */}
      <LandingHero
        set={openingSpotlightSet}
        chaseCards={openingChaseCards}
        sealedProducts={openingSealedProducts}
        cardsAsOf={openingCardsAsOf}
        marketContext={marketContext}
      />
      <MarketStrip signals={marketSignals} />
      <LevelsSection
        openingSet={openingSpotlightSet}
        setIntelligenceSet={setIntelligenceSpotlightSet}
        setIntelligenceChaseCards={setIntelligenceChaseCards}
        sealedProducts={openingSealedProducts}
        rankingRows={bestSetsRows}
      />
      {/* ROLE 2 — the SAME set "What is driving the set?" introduces above. */}
      <SetIntelligenceSection
        set={setIntelligenceSpotlightSet}
        chaseCards={setIntelligenceChaseCards}
      />
      {/* ROLE 3 — the complete published rankings, nothing withheld. */}
      <ExploreSection
        openingRankingRows={openingRankingRows}
        setValueRankingRows={setValueRankingRows}
      />
      <MethodologySection
        marketContext={marketContext}
        methodologyHref={openingSpotlightSet?.ripScoreHref || "/Explore"}
      />
      <FinalCtaSection />
      <Footer />
    </div>
  );
}
