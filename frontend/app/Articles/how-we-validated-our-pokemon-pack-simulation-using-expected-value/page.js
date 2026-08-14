import { ArticleJsonLd, ArticleShell, EditorialSplit, H2, MediaFigure, PackArt } from "@/components/articles/ArticlePrimitives";
import { ARTICLE_PATHS, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "How We Validated Our Pokémon Pack Simulation Using Expected Value";
const description = "How inDex compares analytical Expected Value with simulated mean pack value to validate Pokémon pack simulations, and what matching means cannot prove.";
export const metadata = buildRouteMetadata({ path: "/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value", title: `${title} | inDex`, description, ogTitle: title });
export default function Page() { return <ArticleShell category="Methodology" title={title} deck="The simulator looked plausible, but plausible was not enough. Expected Value gave me a result it should reproduce under the same assumptions." related={related("simulation", "ev", "rip")}>
  <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.validation} />
  <EditorialSplit media={<PackArt src="/images/pokemon/booster-packs/whiteFlare.webp" alt="White Flare Pokemon booster pack" compact />}>
    <p>The simulator looked believable, but that was not a test. I wanted a reference point that did not depend on random sampling.</p>
    <p className="mt-4">If the direct calculation and the simulator read the same pack model and card values, they should reach the same long-run average by different routes. If they do not, something is wrong.</p>
  </EditorialSplit>
  <H2>Analytical EV and simulated EV</H2>
  <p>Analytical Expected Value is the sum of each outcome value multiplied by its probability. In compact form:</p>
  <MediaFigure caption="The project calculates card and slot contributions from the configured probability model, then aggregates them into expected value."><div className="overflow-x-auto py-6 text-center text-xl font-semibold text-[var(--text-primary)]">EV = Σ probability × outcome value</div></MediaFigure>
  <p>Simulated EV is simpler to describe. Run the modeled opening repeatedly, add every simulated pack value, and divide by the number of openings. That sample mean should converge toward the analytical EV as the run grows.</p>
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
</ArticleShell>; }
