import { ArticleJsonLd, ArticleShell, Citation, EditorialSplit, H2, MediaFigure, PackArt, ReferenceList } from "@/components/articles/ArticlePrimitives";
import { ARTICLE_PATHS, articleByKey, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "How We Validated Our Pokémon Pack Simulation Using Expected Value";
const description = "How inDex compares analytical Expected Value with simulated mean pack value to validate Pokémon pack simulations, and what matching means cannot prove.";
const registeredArticle = articleByKey("validation");
const references = [
  { id: "ref-openstax-expected-value", href: "https://openstax.org/books/introductory-statistics-2e/pages/4-key-terms", citation: "OpenStax. Introductory Statistics 2e. Chapter 4: Key Terms.", note: "Defines expected value as the long-run arithmetic average and gives the discrete probability-distribution formula." },
  { id: "ref-metropolis-ulam", href: "https://doi.org/10.1080/01621459.1949.10483310", citation: "Metropolis, N. & Ulam, S. (1949). “The Monte Carlo Method.” Journal of the American Statistical Association, 44(247), 335–341.", note: "Supports the general Monte Carlo sampling method." },
];
export const metadata = buildRouteMetadata({ path: "/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value", title: `${title} | inDex`, description, ogTitle: title });
export default function Page() { return <ArticleShell category="Methodology" title={title} deck="The simulator looked plausible, but plausible was not enough. Expected Value gave me a result it should reproduce under the same assumptions." lastUpdated={registeredArticle.lastUpdated} related={related("simulation", "ev", "rip")}>
  <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.validation} lastUpdated={registeredArticle.lastUpdated} />
  <EditorialSplit media={<PackArt src="/images/pokemon/booster-packs/whiteFlare.webp" alt="White Flare Pokemon booster pack" compact />}>
    <p>The simulator looked believable, but that was not a test. I wanted a reference point that did not depend on random sampling.</p>
    <p className="mt-4">If the direct calculation and the simulator read the same pack model and card values, they should reach the same long-run average by different routes. If they do not, something is wrong.</p>
  </EditorialSplit>
  <H2>Analytical EV and simulated EV</H2>
  <p>Analytical Expected Value is the sum of each outcome value multiplied by its probability, matching the discrete-distribution definition summarized by <Citation href="https://openstax.org/books/introductory-statistics-2e/pages/4-key-terms">OpenStax</Citation>. In compact form:</p>
  <MediaFigure caption="The project calculates card and slot contributions from the configured probability model, then aggregates them into expected value."><div className="overflow-x-auto py-6 text-center text-xl font-semibold text-[var(--text-primary)]">EV = Σ probability × outcome value</div></MediaFigure>
  <p>Simulated EV is simpler to describe. Run the modeled opening repeatedly using a Monte Carlo approach of the kind introduced by <Citation href="https://doi.org/10.1080/01621459.1949.10483310">Metropolis and Ulam</Citation>, add every simulated pack value, and divide by the number of openings. Under the shared model assumptions, that sample mean should converge toward the analytical EV as the run grows.</p>
  <p>The production result stores both values separately: <code>calculated_expected_value_per_pack</code> for the analytical path and the simulation mean for the Monte Carlo path. Keeping both is useful because one is not copied from the other.</p>
  <H2>What I actually test</H2>
  <p>The repository tests the simulation at several levels. Pack-state tests check that probabilities normalize, every state has the required slots, pool tokens resolve, and impossible combinations are rejected. Sampling-integrity tests exercise rarity and state frequencies. Runner tests verify that analytical EV and simulated mean remain distinct published metrics.</p>
  <p>There are also targeted regression tests for sets whose pack structures need special handling, including pattern-card exclusions, overlapping pools, god packs, and set-specific state overrides. Those tests are more useful than one universal assertion because a simulator can be correct for a plain pack and wrong for a special one.</p>
  <p>I am deliberately not publishing a made-up convergence percentage here. The repository defines the methods and test contracts, but it does not contain a current, public, set-by-set validation table with a calculation date that I can responsibly quote as a universal result.</p>
  <H2>What matching EV tells me</H2>
  <p>If the simulated mean settles near the analytical EV under the same input model, that increases confidence that the simulation is sampling the intended probabilities and assigning values consistently. A large persistent gap is a useful alarm. It usually means the calculation and simulation disagree about a pool, a slot, a probability, or which card value applies.</p>
  <H2>What it does not tell me</H2>
  <p>Two distributions can have the same mean and completely different medians, break-even rates, and tails. So matching EV does not prove P50, P95, P99, or the top 1% composition is correct. That is why the repository also tests pack states, special paths, pool membership, no-overlap rules, and sampling behavior directly.</p>
  <p>It also cannot validate the real-world pull-rate assumption. Analytical EV and simulated EV can agree perfectly while both consume the same wrong probability. This check validates implementation consistency inside the model. It does not turn the model into an official description of Pokémon production.</p>
  <H2>References</H2>
  <p>These references support the Expected Value definition and general Monte Carlo method. They do not validate inDex’s Pokémon-specific inputs; the analytical-versus-simulated comparison tests internal model consistency only.</p>
  <ReferenceList items={references} />
</ArticleShell>; }
