import Link from "next/link";
import { ArticleJsonLd, ArticleShell, DefinitionGrid, EditorialSplit, H2, PackArt } from "@/components/articles/ArticlePrimitives";
import { ChaseEfficiencyCoverageFigure, ChaseEfficiencyInputsFigure, ChaseEfficiencyRouteCostFigure, ChaseProbabilityMilestonesFigure, ExactPrintingFigure } from "@/components/articles/ChaseEfficiencyFigures";
import { ARTICLE_PATHS, articleByKey, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

const title = "How Chase Efficiency Measures the Economics of Chasing a Pokémon Card";
const description = "How inDex combines exact card value, modeled pull odds, and verified opening costs to measure how economically favorable a specific Pokémon card is to chase through packs.";
const registeredArticle = articleByKey("chaseEfficiency");

export const metadata = buildRouteMetadata({
  path: "/Articles/how-chase-efficiency-works",
  title: "Pokémon Chase Efficiency: How inDex Measures Card Chases | inDex",
  description,
  ogTitle: title,
});

export default function Page() {
  return <ArticleShell category="Methodology" title={title} deck="I wanted a card-level answer to a question pull odds alone could not answer: if I am opening specifically for this exact printing, how favorable is that chase compared with buying the card—and compared with other chases?" lastUpdated={registeredArticle.lastUpdated} related={related("financial", "ev", "simulation", "rip")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.chaseEfficiency} lastUpdated={registeredArticle.lastUpdated} />

    <EditorialSplit media={<PackArt src="/images/pokemon/booster-packs/stellarCrown.webp" alt="Stellar Crown Pokémon booster pack" compact />}>
      <p>I already had tools for asking whether a set or product was favorable to open. Once individual card pages existed, I realized there was still a different question I could not answer.</p>
      <p className="mt-4">Pull odds tell me how hard a card is to hit. Market price tells me what the card is worth. Neither tells me how economically favorable the chase itself is.</p>
    </EditorialSplit>

    <p>Two $100 cards can have radically different pull rates. Two cards with identical pull rates can live inside packs costing $5 versus $20. Price alone and probability alone are both incomplete.</p>
    <p><strong>Chase Efficiency measures how economically favorable a card is to pursue through opening packs relative to buying the card outright.</strong> In plainer language: which cards give you the best pull opportunity for what they’re worth?</p>
    <p>It is a comparative chase measure—not profitability, expected return, or guaranteed savings. A high-Chase-Efficiency card can still live inside a negative-EV product.</p>

    <H2>The three things a chase actually depends on</H2>
    <ChaseEfficiencyInputsFigure />
    <DefinitionGrid columns="md:grid-cols-3" items={[
      ["Current card value", "The current Near Mint market value of the exact printing. Higher value makes successfully hitting that target more economically consequential."],
      ["Exact modeled pull probability", "The current modeled per-pack probability for that exact printing. A better hit probability improves the chase, but it does not decide the answer alone."],
      ["Best verified opening cost", "The cheapest current pack-equivalent cost across supported products whose random-pack composition is known. Lower opening cost improves the chase."],
    ]} />

    <H2>The unit is the exact printing</H2>
    <EditorialSplit media={<ExactPrintingFigure />} mediaFirst>
      <p>inDex does not rank a Pokémon name generically. The ranked entity is the exact card printing or variant.</p>
      <p className="mt-4">Different printings can have different market prices, printing types, treatments, pull probabilities, and eligibility in the modeled pack configuration. Collapsing them into one Pokémon-level identity would blur the thing I am actually trying to measure.</p>
    </EditorialSplit>

    <H2>Why I stopped treating “pack price” as one number</H2>
    <p>The same random pack can often be acquired through a loose or sleeved booster, a booster bundle, a booster box, or another supported modeled sealed format. Chase Efficiency therefore does not blindly use the loose booster price.</p>
    <p className="rounded-xl border border-[var(--border-subtle)] bg-white/[.035] p-4 text-center font-semibold text-[var(--text-primary)]">pack-equivalent cost = current product price / verified random pack count</p>
    <p>For every eligible route, the rank basis uses the minimum verified current pack-equivalent cost. Pack counts are never inferred: product composition must already be verified by the model. I use the full product price and do not subtract accessory value, promos, or incidental pull recovery. Unsupported or unresolved products do not silently enter the denominator. Loose-pack price remains useful as a comparator; it just is not universal truth.</p>
    <ChaseEfficiencyRouteCostFigure />
    <p>I also tested whether this choice materially mattered. Across the frozen 4,862-printing cohort, recalculating relative position with loose-pack cost still produced a rank-position correlation of approximately 0.993. From far away, the two approaches looked nearly identical.</p>
    <p>Up close, average absolute movement was approximately 119.7 positions, the largest move was 934 positions, and 11 of the 100 cards occupying the leading hundred positions changed. Those identities remain inside Index Premium.</p>
    <p>The two approaches look similar from far away, but they are not interchangeable when the product is meant to rank thousands of card chases precisely. That was enough evidence to reject loose-pack-only pricing as the canonical basis.</p>

    <H2>Pull odds are not Chase Efficiency</H2>
    <DefinitionGrid items={[
      ["Pull Odds", "How difficult is this exact printing to hit?"],
      ["Chase Efficiency", "How economically favorable is that difficulty given what the card is worth and what eligible packs actually cost?"],
    ]} />
    <p>A cheap card with good odds can still be a poor economic chase. An expensive card with terrible odds can also be a poor economic chase. No single input gets to decide the answer, and “more efficient” never means “easy to pull.”</p>

    <H2>Expected packs is not the 50% milestone</H2>
    <p className="rounded-xl border border-[var(--border-subtle)] bg-white/[.035] p-4 text-center font-semibold text-[var(--text-primary)]">P(at least one hit after n packs) = 1 − (1 − p)<sup>n</sup></p>
    <p>The reciprocal, 1 / p, is expected packs per hit in the long run. It is not the pack count where your chance becomes 50%. At n = 1 / p, cumulative probability approaches roughly 63.2% for small p.</p>
    <ChaseProbabilityMilestonesFigure />
    <p>This probability journey prevents “expected packs” from sounding like a guarantee. It is still a model of repeated independent opportunities, not a statement about what a physical box must contain.</p>

    <H2>Ranking and milestone spend solve different problems</H2>
    <p>A canonical ranking needs to stay continuous and independent of an arbitrary probability target, so Chase Efficiency ranks with the best verified pack-equivalent cost. But a real customer cannot buy 3.27 booster boxes.</p>
    <p>For 50%, 75%, 90%, and 95% milestone costs, inDex works in whole supported products. For a product containing <em>k</em> modeled random packs, its modeled hit probability is 1 − (1 − p)<sup>k</sup>. From there, the calculation finds how many whole products are required to reach each target.</p>
    <p>The cheapest product route at 50% does not have to remain cheapest at 75%, 90%, or 95%. Ranking cost basis and whole-product milestone spend are related concepts, but they solve different purchasing questions. I am deliberately not publishing live card milestone dollars here.</p>

    <H2>What Chase Efficiency deliberately does not measure</H2>
    <DefinitionGrid items={[
      ["Total pack profitability", "Not measured. The broader opening-economics question belongs to Financial RIP."],
      ["Incidental card recovery", "Not deducted. Product Chase Economics handles recovery from other pulls as a deliberately separate model."],
      ["Collector desirability", "Not an input. Pokémon popularity and treatment desirability belong to Collector Appeal and Card Intelligence."],
      ["Fees and liquidity", "Near Mint market value is the basis, not a promise of proceeds after seller fees, shipping, condition discounts, liquidity, taxes, or grading costs."],
      ["Physical guarantees", "Modeled pull odds are probabilities under the current pack model, not a guarantee of a hit after exactly N packs."],
    ]} />

    <H2>Financial RIP, Product Chase Economics, and Chase Efficiency are different</H2>
    <DefinitionGrid columns="md:grid-cols-3" items={[
      ["Financial RIP", "How favorable is the overall financial outcome profile of opening this set or product? It reads the full outcome distribution."],
      ["Product Chase Economics", "If I chase this target through this particular sealed product, what does that journey look like? It includes product-specific spend and recovery-adjusted economics."],
      ["Chase Efficiency", "Relative to other exact card printings, how economically favorable is this target through the best verified opening route? It is a cross-card ranking metric."],
    ]} />
    <p>A card can have excellent Chase Efficiency while the product it comes from still has negative expected value. Those statements do not conflict because they answer different questions.</p>

    <H2>I would rather exclude a card than invent an answer</H2>
    <ChaseEfficiencyCoverageFigure />
    <p>The frozen August 27, 2026 publication spans 22 supported sets and 4,862 eligible exact printings. It excludes 17 printings: 9 for stale Near Mint prices and 8 for unmapped canonical card identity.</p>
    <p>Eligibility requires the supported set’s current authoritative simulation run, an exact modeled pull rate, a current and fresh Near Mint card price, canonical exact-printing identity, and at least one verified current opening route.</p>
    <p>Missing inputs never become a neutral value, and stale or inferred data do not enter the ranking. “Unknown” and “average” are not the same thing. If I cannot establish the identity, price, pull rate, and opening route cleanly, I would rather leave the card out than make the ranking look more complete than it really is.</p>

    <H2>Where Chase Efficiency lives in inDex</H2>
    <p>The current hierarchy runs Overall → Eras → Sets → Products → Cards. On the Cards lens in <Link href="/Rankings">RIP Rankings</Link>, Index Premium can rank eligible exact card printings; search by card; filter by era, set, rarity, and market price; and sort by Chase Efficiency and related chase metrics.</p>
    <p>On an individual card page, Index Premium adds card-specific Chase Efficiency context. Rankings and comparative card details live there; this public article explains what the measurement means without reproducing the Premium numeric table. Plan details are available on the <Link href="/pricing">pricing page</Link>.</p>

    <H2>The narrower question</H2>
    <p>When I started building the card layer, I did not want a $1,000 card to look like a great chase just because it was expensive. I did not want a card with good pull odds to look great just because it was easier to hit. And I did not want an expensive loose pack to penalize a chase when a cheaper verified product actually existed.</p>
    <p>That is what Chase Efficiency is trying to solve.</p>
    <p>Financial RIP asks whether opening the product is financially favorable. Pull Odds tell me how difficult one exact printing is to hit. Product Chase Economics tells me what happens if I pursue that target through a particular sealed format.</p>
    <p>Chase Efficiency asks one narrower question: if I am opening specifically for this exact card, how favorable is that chase?</p>
    <p>Separating those questions makes the card layer more useful—and, more importantly, more honest.</p>
  </ArticleShell>;
}
