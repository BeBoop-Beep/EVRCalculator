import { ArticleJsonLd, ArticleShell, DefinitionGrid, DragoniteFigure, EditorialSplit, H2 } from "@/components/articles/ArticlePrimitives";
import { ARTICLE_PATHS, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "How Collector Appeal Measures What Collectors Actually Want";
const description = "How current Collector Appeal measures Pokémon roster desirability and modeled access to desirable cards without using prices, profitability, or financial rank proxies.";
export const metadata = buildRouteMetadata({ path: "/Articles/how-collector-appeal-works", title: `${title} | inDex`, description, ogTitle: title });
export default function Page() { return <ArticleShell category="Methodology" title={title} deck="A pack can be financially efficient and still contain nothing you care about. That is a different problem, so I measure it separately." related={related("rip", "financial", "simulation")}>
  <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.collector} />
  <EditorialSplit media={<DragoniteFigure />}>
    <p>Collector Appeal is not me trying to decide which Pokémon people are allowed to like. It is a structured way to measure two things: does the set have Pokémon collectors care about, and can the modeled pack actually deliver them?</p>
    <p className="mt-4">Dragonite is a good example. Wanting this card is real collector value even if that preference does not make the pack more profitable.</p>
    <p className="mt-4">The current model is Collector Appeal V4. Dual-Path Depth is still shown as a useful diagnostic, but it no longer changes this score.</p>
  </EditorialSplit>
  <H2>The two current factors</H2>
  <DefinitionGrid items={[["Roster Desirability", "How desirable the set’s eligible Pokémon subjects are before pull difficulty. The signal comes from the project’s price-independent desirability system."],["Desirable Outcome Frequency", "The modeled probability that a pack contains at least one card tied to an eligible desirable Pokémon subject. This is not the financial win rate."]]} />
  <p>Roster desirability gives the score its baseline. Desirable Outcome Frequency adjusts for access. A set full of popular Pokémon should not get the same opening assessment if the modeled pack almost never reaches any of them.</p>
  <p>But accessibility is deliberately bounded. It can adjust the result, not bulldoze the roster signal. The protected anchors, modifier budget, and tuning constants are not published.</p>
  <H2>What stays out</H2>
  <p>Collector Appeal does not read card prices, Expected Value, pack cost, profitability, Financial RIP, or a market-rank proxy. That separation is the point. If the collector model quietly used price as a shortcut for desire, Overall RIP would count financial information once on the financial side and then count part of it again under a friendlier name.</p>
  <p>The current subject scope is also narrower than human taste. It models Pokémon. Trainer and artist desirability are not yet modeled, so they are omitted rather than scored as zero. Personal preference is not modeled either. A Dragonite set can matter more to me than its public Collector Appeal suggests, and that is not a failure of arithmetic. It is a boundary of a population-level signal.</p>
  <H2>Why Dual-Path Depth moved</H2>
  <p>Dual-Path Depth asks whether desirable Pokémon offer both an attainable printing and a true elite chase. That is useful information, and inDex retains it as a diagnostic. Current canonical code does not include it in Collector Appeal V4, so this article does not present it as a third factor.</p>
  <H2>Separate from Financial RIP</H2>
  <p>A set can have strong Collector Appeal and weak opening economics. Its roster may be excellent while pack cost is high, losses are deep, or financial value sits in a thin tail. The reverse can happen too: a pack can return value efficiently without having the subjects a collector is excited to chase.</p>
  <p>Overall RIP keeps both perspectives because “worth opening” contains both questions. The financial side carries most of the decision. Collector Appeal adds a smaller, separate view of whether the modeled outcomes are things collectors tend to want. Neither one is a promise about what you personally should like.</p>
</ArticleShell>; }
