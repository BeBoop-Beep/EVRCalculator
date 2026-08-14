import { ArticleJsonLd, ArticleShell, EvDistributionDiagram, H2 } from "@/components/articles/ArticlePrimitives";
import { ARTICLE_PATHS, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
const title = "Why Expected Value Alone Doesn't Tell You Which Pokémon Set Is Best to Open";
const description = "Why Pokémon pack Expected Value is useful but incomplete, and how median outcomes, break-even probability, losses, and tail concentration change the opening decision.";
export const metadata = buildRouteMetadata({ path: "/Articles/why-expected-value-alone-isnt-enough", title: `${title} | inDex`, description, ogTitle: title });
export default function Page() { return <ArticleShell category="Analysis & Guides" title={title} deck="EV answers a real question. The problem is that it is usually not the only question a person opening packs meant to ask." related={related("financial", "simulation", "validation")}>
  <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.ev} />
  <p>I started with Expected Value because financially it is the obvious number to calculate. If a pack has an EV of $4, then across a very large number of openings the modeled average value is $4 per pack. I still show it prominently because that is useful information.</p>
  <p>But a person buying one pack does not receive a fraction of every possible card. They receive one outcome from the distribution, and rare cards can pull the mean a long way away from what normally happens.</p>
  <H2>Same average, different opening</H2>
  <p>Imagine two hypothetical $5 packs with the same $4 EV. In Profile A, a lot of openings land around $3 to $5. In Profile B, most openings land near $1 and a tiny number land far above pack cost. Those averages can match even though the normal experience does not.</p>
  <EvDistributionDiagram />
  <p>The values in that diagram are hypothetical, but the problem is not. Pack distributions are skewed because high-value chase cards are rare. The mean feels those cards every time we calculate it. Most individual openings do not.</p>
  <H2>Mean versus median</H2>
  <p>P50 is the median. Half of simulated openings finish above it and half finish below it. On the site I call that Typical Opening because it is more useful to most people than “50th percentile simulated return.”</p>
  <p>When EV sits well above P50, value is being carried by outcomes above the middle. That is not automatically bad. Some collectors want a high-variance chase. But it is a different bet from a set whose ordinary outcomes retain more of the pack price.</p>
  <H2>Questions EV leaves open</H2>
  <ul className="list-disc space-y-2 pl-5"><li>How often does an opening recover the pack cost?</li><li>When an opening loses, how much value does it usually retain?</li><li>Where does the strongest 5% begin?</li><li>How much of the average depends on the exceptional top 1%?</li></ul>
  <p>Break-even probability answers the first question. Loss resilience looks at the second. P95 and the 95th-to-99th percentile band describe strong but non-jackpot upside. P99 and the top 1% describe the exceptional tail.</p>
  <H2>What EV is good at</H2>
  <p>EV is still the cleanest long-run financial reference. It lets me check whether the simulation mean behaves correctly, compare average return with pack cost, and see whether price changes are improving or weakening a set’s modeled economics.</p>
  <p>I just do not ask it to answer a question it was not built to answer. “What is the average modeled return?” and “Which set is best to open?” overlap, but they are not the same question. Financial RIP is the framework I built for the second one.</p>
</ArticleShell>; }
