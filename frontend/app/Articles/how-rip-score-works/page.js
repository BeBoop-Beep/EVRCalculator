import { ArticleJsonLd, ArticleShell, Citation, DefinitionGrid, EditorialSplit, H2, LiveDistributionFigure, MetricStory, PackArt, ReferenceList } from "@/components/articles/ArticlePrimitives";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import { ARTICLE_PATHS, articleByKey, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "How the RIP Score Works";
const description = "Why Expected Value alone was not enough to rank Pokémon sets, how current Overall RIP combines Financial RIP with Collector Appeal, and what the score can and cannot tell you.";
const registeredArticle = articleByKey("rip");
const references = [
  { id: "ref-openstax-statistics", href: "https://openstax.org/books/introductory-statistics-2e/pages/4-key-terms", citation: "OpenStax. Introductory Statistics 2e. Chapter 4: Key Terms.", note: "Supports the Expected Value and probability-distribution definitions used in the opening analysis." },
  { id: "ref-metropolis-ulam", href: "https://doi.org/10.1080/01621459.1949.10483310", citation: "Metropolis, N. & Ulam, S. (1949). “The Monte Carlo Method.” Journal of the American Statistical Association, 44(247), 335–341.", note: "Supports the general repeated-random-sampling method used to form modeled outcome distributions." },
];
export const metadata = buildRouteMetadata({ path: "/Articles/how-rip-score-works", title: `${title} | inDex`, description, ogTitle: title });
export default async function HowRipScoreWorksArticle() {
  const data = await getLandingPageData();
  return <ArticleShell category="Methodology" title={title} deck="Overall RIP compares modeled opening economics and collector desirability. It is a relative ranking tool, not a promise that your next pack makes money." lastUpdated={registeredArticle.lastUpdated} related={related("financial", "collector", "simulation", "validation")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.rip} lastUpdated={registeredArticle.lastUpdated} />
    <EditorialSplit media={<PackArt />}>
      <p>Expected Value—the long-run mean of a probability distribution as defined by <Citation href="https://openstax.org/books/introductory-statistics-2e/pages/4-key-terms">OpenStax</Citation>—was the first thing I calculated because it is the obvious way to measure a pack financially. It was also the first thing that showed me why EV was not going to be enough.</p>
      <p className="mt-4">Two sets can land on nearly the same EV and still feel completely different to open. One can spread value across cards you actually hit. Another can hide most of its average in one huge chase.</p>
      <p className="mt-4">I would not call those the same opening, so inDex cannot treat them as equivalent.</p>
    </EditorialSplit>
    <H2>Overall RIP</H2>
    <p>The current canonical score is Overall RIP V10 under Public RIP Contract V10. Overall RIP V10 combines Financial RIP V4, which measures the modeled outcome profile relative to pack cost, with Collector Appeal V5, which measures contextual Pokémon desirability and modeled access to desirable outcomes under the existing canonical weighting. The financial side asks how favorable the opening economics are. The collector side asks whether those outcomes are things collectors tend to care about.</p>
    <MetricStory items={[{ label: "Overall RIP", text: "The headline comparison against other supported sets." }, { label: "Financial RIP", text: "What the modeled wins, losses, and upside look like against pack cost." }, { label: "Collector Appeal", text: "Whether the set contains desirable Pokémon and how often the model can reach them." }]} />
    <p>The canonical ranking authority is normalized on a 0–100 basis internally, while the current inDex product presents that result as a 0–10 RIP score. A displayed 9.2 does not mean a 92% chance of profit, 92% value retention, or an objectively excellent product. It means the set compares strongly with the eligible cohort under the current model.</p>
    <p>A displayed 10.0 means the strongest current relative comparison, not a perfect or guaranteed opening. Because the presentation is cohort-relative, a displayed score can move when the comparison group changes even if the set’s fixed model score does not. The backend retains the underlying authority values for audit while product surfaces show the 0–10 presentation.</p>
    <H2>Financial RIP</H2>
    <p>Financial RIP reads the simulated pack values and the cost used for the run. It does not consume Collector Appeal or Pokémon popularity.</p>
    <DefinitionGrid items={[["True Win Frequency", "How often modeled value reaches or exceeds pack cost."],["Typical Retention", "How much of pack cost the median opening retains."],["Loss Resilience", "How deep and how frequent losing outcomes are."],["Strong Upside Quality", "The P95 threshold relative to cost defines the current V4 scoring signal. The P95–P99 conditional mean remains descriptive context, not a V4 score input."],["Jackpot Upside", "The P99 threshold and top 1%, controlled so a giant chase cannot dominate."],["Base Economic Efficiency", "Average return relative to cost after excluding the top 1%."]]} />
    <p>The exact weights, anchors, caps, and tuning constants are protected. The dimensions and their behavior are public because a reader should be able to understand what the model rewards and criticize that choice without receiving a cloneable recipe.</p>
    <H2>Collector Appeal</H2>
    <p>Collector Appeal V5 uses a contextual Pokémon desirability baseline and a Desirable Outcome Frequency adjustment. Market price, Expected Value, profitability, pack cost, and Financial RIP are not directly added to its score arithmetic. However, same-run card EV contribution provides contextual evidence for which Pokémon meaningfully represent the set’s chase roster. EV establishes relevance; it is not multiplied into Pokémon desirability or treated as a financial score.</p>
    <p>Dual-Path Depth remains visible as a diagnostic, but it is not a Collector Appeal V5 score input.</p>
    <p>This is narrower than “what people like.” It currently models Pokémon subjects, not trainers, artists, or personal favorites. Missing coverage makes the result unavailable instead of forcing an absent signal to zero.</p>
    <H2>The simulation underneath it</H2>
    <p>Supported sets run through one million modeled openings using repeated random sampling in the general Monte Carlo tradition described by <Citation href="https://doi.org/10.1080/01621459.1949.10483310">Metropolis and Ulam</Citation>. The project-specific pack states, card pools, pull assumptions, and current calculation values produce the distribution that supplies P50, P95, P99, break-even behavior, loss behavior, and the Financial RIP inputs.</p>
    <LiveDistributionFigure distribution={data.openingDistribution} setName={data.openingSpotlightSet?.name || "the featured set"} simulationCount={data.openingSpotlightSet?.simulationCount} />
    <p>A million trials reduce sampling noise. They do not validate the real-world assumptions by themselves. If a pull-rate model is wrong, more trials make the wrong model look steadier. That is why inDex describes these as modeled pull rates, tests the pack-state logic separately, and leaves unsupported sets unranked.</p>
    <H2>What the score leaves out</H2>
    <p>Displayed card value is not guaranteed cash in hand. Liquidity, seller fees, taxes, shipping, grading, and regional price differences can all separate modeled value from realized proceeds. Markets and pack costs also move, so each result belongs to a calculation snapshot rather than being a permanent property of the set.</p>
    <p>Overall RIP is useful for one job: ordering the supported choices in front of you using a consistent opening model. It is not financial advice, a forecast, or a prediction of your next pack.</p>
    <H2>References</H2>
    <p>Overall RIP and its combination of Financial RIP with Collector Appeal are original inDex methodology. These references support the standard Expected Value, probability-distribution, and Monte Carlo concepts underneath the analysis; they do not externally validate the RIP score or disclose its protected construction.</p>
    <ReferenceList items={references} />
  </ArticleShell>;
}
