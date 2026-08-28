import { ArticleJsonLd, ArticleShell, Citation, DefinitionGrid, EditorialSplit, H2, LiveDistributionFigure, PackArt, ReferenceList } from "@/components/articles/ArticlePrimitives";
import { getLandingPageData } from "@/lib/landing/landingHeroServer";
import { ARTICLE_PATHS, articleByKey, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

const title = "How We Simulated One Million Pokémon Pack Openings";
const description = "How the inDex Pokémon pack simulation builds an outcome distribution, what its percentiles mean, and what one million modeled openings cannot prove.";
const registeredArticle = articleByKey("simulation");
const references = [{ id: "ref-metropolis-ulam", href: "https://doi.org/10.1080/01621459.1949.10483310", citation: "Metropolis, N. & Ulam, S. (1949). “The Monte Carlo Method.” Journal of the American Statistical Association, 44(247), 335–341.", note: "Supports the general use of repeated random sampling as a computational method." }];
export const metadata = buildRouteMetadata({ path: "/Articles/how-we-simulated-one-million-pokemon-pack-openings", title: `${title} | inDex`, description, ogTitle: title });

export default async function Page() {
  const data = await getLandingPageData();
  const set = data.openingSpotlightSet;
  return <ArticleShell category="Methodology" title={title} deck="One pack gives you a story. A million modeled packs give us a distribution we can actually measure." lastUpdated={registeredArticle.lastUpdated} related={related("validation", "rip", "ev")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.simulation} lastUpdated={registeredArticle.lastUpdated} />
    <EditorialSplit media={<PackArt src="/images/pokemon/booster-packs/megaEvolution.webp" alt="Mega Evolution Pokemon booster pack" compact />}>
      <p>One exciting pack tells me almost nothing about a set. I wanted to see every kind of opening the model could produce, including the ordinary losses nobody posts and the rare pulls everybody remembers.</p>
      <p className="mt-4">Expected Value gives me the average. It does not show how often a pack breaks even, what a normal result looks like, or how far away the jackpot sits. That is where simulation became useful.</p>
    </EditorialSplit>
    <H2>What one simulated opening does</H2>
    <p>The simulator starts with the configured pack structure for a set. It chooses a valid pack state from the modeled state probabilities, resolves the rare and reverse slots for that state, samples eligible cards from the corresponding pools, and adds the current modeled card values. Special pack paths and set-specific constraints are handled by their configured rules.</p>
    <p>That last part matters. The engine does not independently roll every rarity and hope the combination resembles a real pack. The current V2 path models complete pack states and validates that state probabilities add to one, required pools exist, and incompatible hit combinations do not slip through.</p>
    <p>Then it does the same thing again. This repeated-random-sampling approach is the general idea behind Monte Carlo methods described by <Citation href="https://doi.org/10.1080/01621459.1949.10483310">Metropolis and Ulam</Citation>. The production runner requests 1,000,000 openings per supported set and stores the value of each opening long enough to compute the outcome profile and Financial RIP inputs.</p>
    <H2>Why the distribution matters</H2>
    <p>An average is one coordinate. The distribution shows how much probability sits around low-value openings, where the middle lands, and how quickly the rare upside stretches away from everything else.</p>
    <LiveDistributionFigure distribution={data.openingDistribution} setName={set?.name || "the featured set"} simulationCount={set?.simulationCount} />
    <DefinitionGrid items={[["Expected Value", "The simulated mean across all modeled openings."],["Typical Opening, P50", "The median. Half of modeled openings finish below it and half finish above it."],["Strong Upside, P95", "The threshold where the strongest 5% of modeled openings begins."],["Jackpot Upside, P99", "The threshold where the top 1% begins."],["Break-even probability", "The share of modeled openings whose value is at least the pack cost used for that run."],["Loss behavior", "How often openings lose, how much losing openings retain, and whether losses cluster near cost or far below it."]]} />
    <H2>Why one million</H2>
    <p>I use a large run because percentiles in the tail are noisy when the sample is small. More trials reduce that sampling noise and give the top 1% enough observations for its conditional measurements. The scoring code refuses a Financial RIP result when the run is too small for that tail to be supported.</p>
    <p>One million is not a magic line where the model becomes true. It is the production trial count and it makes repeated sampling much steadier. A different random run can still move slightly.</p>
    <H2>What the simulation cannot prove</H2>
    <p>Running one million simulations reduces sampling noise. It does not make a bad pull-rate assumption correct. If the assumptions going in are wrong, running the model more times gives us a more precise version of the wrong answer.</p>
    <p>The pull-rate inputs are modeled assumptions assembled from the set configuration and the available evidence. They are not comprehensive official Pokémon pull rates. Coverage also varies by set, so inDex leaves unsupported simulations unavailable instead of quietly substituting a generic model.</p>
    <p>So when I call P50 a Typical Opening, I mean typical inside this published model, at the card values and pack cost attached to that calculation snapshot. It is evidence for comparing modeled opening profiles. It is not a prediction of the next wrapper you tear open.</p>
    <H2>References</H2>
    <p>The inDex pack-state architecture, Pokémon-specific state configuration, constraints, and pull assumptions are project-specific implementations rather than methods described by Metropolis and Ulam. The reference supports the general Monte Carlo approach, not the accuracy of the Pokémon model.</p>
    <ReferenceList items={references} />
  </ArticleShell>;
}
