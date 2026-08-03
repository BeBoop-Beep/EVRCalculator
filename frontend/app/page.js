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
    heroSet,
    featureSet,
    heroChaseCards,
    heroSealedProducts,
    heroCardsAsOf,
    featureChaseCards,
    marketSignals,
    bestSets,
    exploreRows,
    setValueLeaders,
    marketContext,
  } = await getLandingPageData();

  return (
    <div className={styles.page}>
      <LandingHero
        set={heroSet}
        chaseCards={heroChaseCards}
        sealedProducts={heroSealedProducts}
        cardsAsOf={heroCardsAsOf}
        marketContext={marketContext}
      />
      <MarketStrip signals={marketSignals} />
      <LevelsSection
        set={heroSet}
        chaseCards={heroChaseCards}
        sealedProducts={heroSealedProducts}
        exploreRows={bestSets}
      />
      {/* A different real set from the hero wherever more than one is
          published, so the page demonstrates breadth. */}
      <SetIntelligenceSection set={featureSet} chaseCards={featureChaseCards} />
      <ExploreSection
        exploreRows={exploreRows}
        setValueLeaders={setValueLeaders}
        leadCard={heroChaseCards[0] || null}
      />
      <MethodologySection
        marketContext={marketContext}
        methodologyHref={heroSet?.ripScoreHref || "/Explore"}
      />
      <FinalCtaSection />
      <Footer />
    </div>
  );
}
