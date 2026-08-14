import { ArticleJsonLd, ArticleShell, DefinitionGrid, EditorialSplit, H2, LiveDistributionFigure, MetricStory, PackArt } from "@/components/articles/ArticlePrimitives";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import { ARTICLE_PATHS, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "How the RIP Score Works";
const description = "Why Expected Value alone was not enough to rank Pokémon sets, how current Overall RIP combines Financial RIP with Collector Appeal, and what the score can and cannot tell you.";
export const metadata = buildRouteMetadata({ path: "/Articles/how-rip-score-works", title: `${title} | inDex`, description, ogTitle: title });
export default async function HowRipScoreWorksArticle() {
  const data = await getLandingPageData();
  return <ArticleShell category="Methodology" title={title} deck="Overall RIP compares modeled opening economics and collector desirability. It is a relative ranking tool, not a promise that your next pack makes money." related={related("financial", "collector", "simulation", "validation")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.rip} />
    <EditorialSplit media={<PackArt />}>
      <p>Expected Value was the first thing I calculated because it is the obvious way to measure a pack financially. It was also the first thing that showed me why EV was not going to be enough.</p>
      <p className="mt-4">Two sets can land on nearly the same EV and still feel completely different to open. One can spread value across cards you actually hit. Another can hide most of its average in one huge chase.</p>
      <p className="mt-4">I would not call those the same opening, so inDex cannot treat them as equivalent.</p>
    </EditorialSplit>
    <H2>Overall RIP</H2>
    <p>The current canonical score is Overall RIP V8. It combines Financial RIP V3, which measures the modeled outcome profile relative to pack cost, with Collector Appeal V4, which measures roster desirability and modeled access to desirable Pokémon. The financial side answers whether the opening math works. The collector side asks whether those outcomes are things collectors tend to care about.</p>
    <MetricStory items={[{ label: "Overall RIP", text: "The headline comparison against other supported sets." }, { label: "Financial RIP", text: "What the modeled wins, losses, and upside look like against pack cost." }, { label: "Collector Appeal", text: "Whether the set contains desirable Pokémon and how often the model can reach them." }]} />
    <p>The public 0 to 100 scale is relative. The strongest eligible set in the current comparison group is 100 and everything else is standardized against that cohort. A 92 does not mean a 92% chance of profit, 92% value retention, or an objectively excellent product. It means the set compares strongly with the supported sets ranked beside it.</p>
    <p>Because the presentation is cohort-relative, a public score can move when the comparison group changes even if the set’s fixed model score does not. The current backend publishes both identities for audit, while normal product surfaces show the relative number.</p>
    <H2>Financial RIP</H2>
    <p>Financial RIP reads the simulated pack values and the cost used for the run. It does not consume Collector Appeal or Pokémon popularity.</p>
    <DefinitionGrid items={[["True Win Frequency", "How often modeled value reaches or exceeds pack cost."],["Typical Retention", "How much of pack cost the median opening retains."],["Loss Resilience", "How deep and how frequent losing outcomes are."],["Strong Upside Quality", "The P95 threshold and the quality of the 95th-to-99th percentile band."],["Jackpot Upside", "The P99 threshold and top 1%, controlled so a giant chase cannot dominate."],["Base Economic Efficiency", "Average return relative to cost after excluding the top 1%."]]} />
    <p>The exact weights, anchors, caps, and tuning constants are protected. The dimensions and their behavior are public because a reader should be able to understand what the model rewards and criticize that choice without receiving a cloneable recipe.</p>
    <H2>Collector Appeal</H2>
    <p>Collector Appeal V4 uses two price-independent factors: Roster Desirability and Desirable Outcome Frequency. It does not read prices, EV, profitability, pack cost, or Financial RIP. Dual-Path Depth remains visible as a diagnostic but is not a V4 score input.</p>
    <p>This is narrower than “what people like.” It currently models Pokémon subjects, not trainers, artists, or personal favorites. Missing coverage makes the result unavailable instead of forcing an absent signal to zero.</p>
    <H2>The simulation underneath it</H2>
    <p>Supported sets run through one million modeled openings using their configured pack states, card pools, pull assumptions, and current calculation values. That distribution supplies P50, P95, P99, break-even behavior, loss behavior, and the Financial RIP inputs.</p>
    <LiveDistributionFigure distribution={data.openingDistribution} setName={data.openingSpotlightSet?.name || "the featured set"} simulationCount={data.openingSpotlightSet?.simulationCount} />
    <p>A million trials reduce sampling noise. They do not validate the real-world assumptions by themselves. If a pull-rate model is wrong, more trials make the wrong model look steadier. That is why inDex describes these as modeled pull rates, tests the pack-state logic separately, and leaves unsupported sets unranked.</p>
    <H2>What the score leaves out</H2>
    <p>Displayed card value is not guaranteed cash in hand. Liquidity, seller fees, taxes, shipping, grading, and regional price differences can all separate modeled value from realized proceeds. Markets and pack costs also move, so each result belongs to a calculation snapshot rather than being a permanent property of the set.</p>
    <p>Overall RIP is useful for one job: ordering the supported choices in front of you using a consistent opening model. It is not financial advice, a forecast, or a prediction of your next pack.</p>
  </ArticleShell>;
}
