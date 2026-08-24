import Link from "next/link";
import { ArticleJsonLd, ArticleShell, Citation, DefinitionGrid, EditorialSplit, H2, H3, MediaFigure, MetricStory, PackArt, ReferenceList } from "@/components/articles/ArticlePrimitives";
import { OutcomeProbabilityFigure, TailConvergenceFigure, TypicalVsEvFigure } from "@/components/articles/EvRepresentativenessResearchFigures";
import { LivePrismaticDistribution, LivePrismaticEvRepresentativeness, LivePrismaticOutcomeProfile } from "@/components/articles/EvResearchLiveExamples";
import { ARTICLE_PATHS, related } from "@/lib/articles/articleData.mjs";
import { selectPrismaticResearchLiveExample } from "@/lib/articles/evResearchLiveExample.mjs";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getPokemonSetSimulationEvidenceInitialSnapshot } from "@/lib/pokemon/pokemonSetInitialSnapshotsServer";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { toSetSlug } from "@/utils/slugify";

const title = "How Well Does Expected Value Describe a Pokémon Pack Opening?";
const description = "We analyzed 22 million modeled Pokémon pack outcomes across 22 sets to measure how closely Expected Value reflects typical openings, how much EV depends on rare outcomes, and how many packs it can take for realized averages to converge.";

export const metadata = buildRouteMetadata({
  path: "/Articles/how-representative-is-pokemon-pack-expected-value",
  title: "Pokémon Pack Expected Value vs Real Outcomes: 22 Million Simulations | inDex",
  description,
  ogTitle: title,
});

const setHref = name => `/TCGs/Pokemon/Sets/${encodeURIComponent(toSetSlug(name))}`;
const references = [
  { id: "ref-metropolis-ulam", href: "https://doi.org/10.1080/01621459.1949.10483310", citation: "Metropolis, N. & Ulam, S. (1949). “The Monte Carlo Method.” Journal of the American Statistical Association, 44(247), 335–341." },
  { id: "ref-wilson", href: "https://doi.org/10.1080/01621459.1927.10502953", citation: "Wilson, E. B. (1927). “Probable Inference, the Law of Succession, and Statistical Inference.” Journal of the American Statistical Association, 22(158), 209–212." },
  { id: "ref-efron", href: "https://doi.org/10.1214/aos/1176344552", citation: "Efron, B. (1979). “Bootstrap Methods: Another Look at the Jackknife.” The Annals of Statistics, 7(1), 1–26." },
  { id: "ref-spearman", href: "https://doi.org/10.2307/1412159", citation: "Spearman, C. (1904). “The Proof and Measurement of Association between Two Things.” The American Journal of Psychology, 15(1), 72–101." },
  { id: "ref-benjamini-hochberg", href: "https://doi.org/10.1111/j.2517-6161.1995.tb02031.x", citation: "Benjamini, Y. & Hochberg, Y. (1995). “Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing.” Journal of the Royal Statistical Society: Series B, 57(1), 289–300." },
  { id: "ref-glasserman", href: "https://doi.org/10.1007/978-0-387-21617-1", citation: "Glasserman, P. (2003). Monte Carlo Methods in Financial Engineering. Springer." },
];

async function loadLivePrismaticExample() {
  try {
    const targetsPayload = await getRipStatisticsTargets({ limit: 150 });
    const target = (Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : []).find((row) => row?.target_type === "set" && String(row?.name || "").trim().toLowerCase() === "prismatic evolutions");
    if (!target?.target_id) return null;
    const snapshot = await getPokemonSetSimulationEvidenceInitialSnapshot(target.target_id);
    const model = selectPrismaticResearchLiveExample(target, snapshot?.payload);
    return model ? { ...model, setHref: setHref("Prismatic Evolutions") } : null;
  } catch {
    return null;
  }
}

export default async function Page() {
  const livePrismatic = await loadLivePrismaticExample();
  return <ArticleShell category="Research" title={title} deck="I simulated one million pack outcomes for each of 22 Pokémon sets, then asked a different question: not whether Expected Value was mathematically correct, but how closely it actually describes what a real opener experiences." related={related("ev", "simulation", "validation", "financial")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.evRepresentativeness} />

    <EditorialSplit media={<PackArt src="/images/pokemon/booster-packs/prismaticEvolutions.webp" alt="Prismatic Evolutions Pokémon booster pack" compact />}>
      <p>I simulated a million Pokémon pack openings because I wanted to know what you actually get when you open one. The first obvious answer was Expected Value.</p>
      <p className="mt-4">If a pack has an EV of $8.53, its modeled average is $8.53. That is correct. But the more I looked at the outcomes, the stranger that answer started to feel. For Prismatic Evolutions, the middle modeled opening was only $1.78.</p>
    </EditorialSplit>

    <p>I was asking one average to do two jobs. It could tell me the long-run mean. It could not, by itself, tell me whether a normal person opening a realistic number of packs would see anything close to that mean.</p>
    <p>So I changed the question: <strong>how many packs does it take before Expected Value starts describing realized opening experience reasonably well?</strong></p>
    <p>This article documents the frozen answer as of August 22, 2026: 22 supported sets, each with its own authoritative one-million-outcome artifact. That is 22,000,000 exact modeled one-pack outcomes across the cohort—not one pooled 22-million-pack simulation. Production still models one million openings per supported set.</p>

    <H2>EV is an average, not a typical outcome</H2>
    <p>Let <em>X</em> be the gross modeled card market value returned by one opening, and let its mean be μ. Then E[X] = μ. If I average <em>N</em> independent modeled openings, E[X̄<sub>N</sub>] = μ for every <em>N</em>, including one.</p>
    <MediaFigure caption="The expectation does not change with pack count. The spread of realized sample averages does."><div className="overflow-x-auto py-5 text-center text-lg font-semibold text-[var(--text-primary)]"><span className="whitespace-nowrap">E[X] = μ</span><span className="mx-4 text-[var(--accent)]" aria-hidden="true">and</span><span className="whitespace-nowrap">E[X̄<sub>N</sub>] = μ for every N</span></div></MediaFigure>
    <p>That distinction matters. EV does not “become correct” after enough packs. It is already the expected mean. What changes as <em>N</em> grows is concentration: actual sample averages become more likely to sit near that expectation. The average does not become more correct. Your realized results become more likely to look like the average.</p>
    <p>Why can one opening feel so far away? Pokémon pack values are positively skewed. Many outcomes cluster low, while a small number of expensive pulls stretch the right tail. The mean responds to every dollar in that tail. The median, or P50, tells me where the middle modeled opening lands. A real opener does not receive a tiny fraction of every card; they receive one realized outcome.</p>
    <LivePrismaticDistribution model={livePrismatic} />
    <p>I introduced that conceptual problem in <Link href={ARTICLE_PATHS.ev}>Why Expected Value Alone Isn’t Enough</Link>. This study goes further: it measures the gap, tests finite opening sessions, and asks which features of a set explain why the gap persists.</p>

    <H2>What I measured</H2>
    <p>I wanted a small group of statistics that each answered a distinct question. I did not want a new score looking authoritative merely because several measurements had been blended together.</p>
    <DefinitionGrid items={[
      ["Typical Capture", "P50 ÷ EV. How much of the long-run average is present in the middle modeled opening."],
      ["Top 1% EV Contribution", "The exact share of total modeled value contributed by the highest-value 1% of openings."],
      ["80% EV Horizon", "The minimum confirmed pack count where at least 80% of modeled openers average at least 80% of EV."],
      ["EV Convergence Horizon", "The minimum confirmed pack count where at least 80% of modeled openers finish within ±20% of EV."],
    ]} />

    <H3>Typical Capture</H3>
    <p>Typical Capture = P50 / EV. If EV is $10 and the median modeled opening is $3, Typical Capture is 30%. The middle opening captures 30% of the long-run average. It is a ratio, not a probability: it does not mean there is a 30% chance of receiving EV.</p>

    <H3>Top 1% EV Contribution</H3>
    <p>This measures how much of all simulated value lives in the highest-value 1% of outcomes. Ties make a naïve “value greater than or equal to P99” rule unreliable because the P99 value can occur many times. The study instead takes exact rank mass: <span className="whitespace-nowrap">k = max(1, ceil(nq))</span>. In ordinary language, it selects exactly the required number of top-ranked observations, even when values tie.</p>

    <H3>Two finite-sample horizons</H3>
    <p>The realization question is R<sub>N</sub>(.80) = P(X̄<sub>N</sub> ≥ .80 EV): how often does an <em>N</em>-pack average reach at least 80% of EV? The public 80% EV Horizon is the minimum <em>confirmed</em> N where that probability meets the 80% opener standard.</p>
    <p>The convergence question is C<sub>N</sub>(.20) = P(|X̄<sub>N</sub> − EV| / EV ≤ .20): how often does the realized average land within 20% on either side of EV? Its public horizon also uses an 80% opener standard. Neither number says EV suddenly becomes valid there. Each describes a specific concentration target.</p>

    <H2>How I tested it</H2>
    <p>The one-pack authority was what the research calls Tier A. It reads the exact persisted one-million-outcome float64 artifact for each set and verifies the file with SHA-256. It does not resimulate the public one-pack metrics. The median, EV, outcome buckets, and tail shares therefore come from the exact saved run.</p>
    <p>Tier B is separate. It deterministically reconstructs openings when the research needs latent card identity for card attribution, paired price shocks, or counterfactuals. I did not treat that reconstruction as authoritative until its mean and quantiles reconciled against Tier A. Tier B is also not the production simulator: production remains independently stochastic and unseeded.</p>
    <p>The broad simulation approach follows the Monte Carlo tradition described by <Citation href="https://doi.org/10.1080/01621459.1949.10483310">Metropolis and Ulam</Citation>. For finite sessions, I sampled with replacement from each exact empirical one-pack distribution. This is an empirical bootstrap approach in the sense established by <Citation href="https://doi.org/10.1214/aos/1176344552">Efron</Citation>: the observed million-outcome distribution becomes the population from which realistic N-pack sessions are constructed.</p>
    <p>The natural grid included 1, 6, 9, 11, 18, 36, 50, 100, 150, 250, 500, 750, and 1,000 packs, with additional refinement when a horizon lay between or beyond those points. Session paths share random draws across the ascending grid, a common-random-numbers technique that reduces comparison noise; this kind of simulation design is discussed more broadly by <Citation href="https://doi.org/10.1007/978-0-387-21617-1">Glasserman</Citation>.</p>

    <H3>I did not accept the first noisy crossing</H3>
    <p>A Monte Carlo probability curve can bounce above and below 80%. The sampling estimate still contains noise, and the underlying discrete session distribution does not have to move monotonically at every integer pack count. Binary-searching a supposedly monotonic curve would have assumed away the exact behavior I needed to test.</p>
    <p>For every probability, the study calculated a 95% Wilson score interval, following <Citation href="https://doi.org/10.1080/01621459.1927.10502953">Wilson’s score-based method</Citation>. A candidate horizon had to clear the target with the interval’s lower bound, remain stable across a validation band, and survive a separate 250,000-session confirmation run. First crossings remain useful diagnostics, but they stay internal when confirmation does not ratify them.</p>
    <MetricStory items={[
      { label: "Estimate", text: "Calculate the empirical opener probability over the full grid." },
      { label: "Stability", text: "Require the Wilson 95% lower bound to clear the target across a validation band." },
      { label: "Confirm", text: "Re-estimate with an independent 250,000-session stream before publishing the horizon." },
    ]} />

    <H2>The first result that surprised me</H2>
    <p>Across the 22 sets, Typical Capture ranged from 20.9% to 54.9%. That is not a minor difference in presentation. It means the middle modeled opening in one set held barely one-fifth of EV, while another held more than half.</p>
    <TypicalVsEvFigure />
    <p>For <Link href={setHref("Prismatic Evolutions")}>Prismatic Evolutions</Link>, EV was $8.53 and P50 was $1.78, producing 20.9% Typical Capture. The typical modeled opening captured about one-fifth of the long-run average.</p>
    <p>For <Link href={setHref("Journey Together")}>Journey Together</Link>, EV was $3.44 and P50 was $1.89, producing 54.9% Typical Capture. Both distributions were positively skewed. They simply had radically different outcome structures. That does not make either set universally “better”; a person seeking chase-heavy upside and a person seeking stronger ordinary retention are not asking the same question.</p>

    <H2>Some sets need hundreds of packs. Some need thousands.</H2>
    <p>The confirmed horizons made the difference even harder to ignore. Journey Together reached both the 80% EV realization standard and the ±20% convergence standard at about 150 packs. Prismatic Evolutions needed about 2,812 packs for the first standard and 5,906 for the second.</p>
    <p>Other chase-heavy examples sat between them. Phantasmal Flames required about 1,167 packs to reach the realization standard and 2,438 to converge within ±20%. Paldean Fates required about 833 and 1,750. Ascended Heroes required about 792 and 1,750.</p>
    <p>Paldea Evolved is a useful example of the confirmation rule doing its job. Its 500-pack convergence candidate did not survive independent confirmation, so its frozen public convergence result is <strong>Not confirmed</strong>. Publishing the first crossing instead would turn a failed check into a headline.</p>
    <p>Those are the frozen cohort results. The panel below shows how the same measurements appear for Prismatic Evolutions using the current published run.</p>
    <LivePrismaticEvRepresentativeness model={livePrismatic} />

    <H2>The biggest clue was the top 1%</H2>
    <p>Prismatic Evolutions concentrated 64.1% of total EV in the highest-value 1% of modeled openings. Its top 10% contributed 80.0%. Journey Together’s top 1% contributed 16.7%. That suggested a simple explanation: when more of the average lives in exceptional outcomes, ordinary sample averages need longer to resemble it.</p>
    <TailConvergenceFigure />
    <p>The full cohort supported that pattern. Top-1% EV contribution versus the ±20%/80% horizon had a Spearman rank correlation of ρ = 0.976, bootstrap 95% CI [0.908, 0.993], with a Benjamini–Hochberg-adjusted p-value of 0.0006. Against the 80% EV Horizon, ρ = 0.966, CI [0.909, 0.986], adjusted p = 0.0006.</p>
    <p>I used Spearman correlation because the question was whether set rankings moved together, without requiring a linear relationship; the method traces to <Citation href="https://doi.org/10.2307/1412159">Spearman’s rank-association work</Citation>. Because the research tested multiple relationships, p-values were corrected using the false-discovery-rate procedure from <Citation href="https://doi.org/10.1111/j.2517-6161.1995.tb02031.x">Benjamini and Hochberg</Citation>.</p>
    <p>This is a cross-set association across 22 observations, not proof of a universal causal law. It is still the strongest observed predictor in this cohort: sets where more EV lived in the extreme opening tail generally took much longer for realized averages to resemble EV.</p>

    <H3>Card concentration is not outcome concentration</H3>
    <p>Individual-card concentration was informative, but it was weaker than realized outcome-tail concentration. Phantasmal Flames, for example, received about 37.4% of EV from its top contributing card. That is a card-level statement. “The top 1% of openings contributed 45.9% of EV” is a distribution-level statement. Pack structure can combine cards, slots, and values in ways that keep those concepts related but not interchangeable.</p>

    <H2>Then I asked a simpler question</H2>
    <p>Knowing why EV behaves this way is useful. But a person deciding whether to open a pack may ask something more direct: what percentage of openings are actually bad?</p>
    <p>I normalized each one-pack result by opening cost: R = X / C, where X is gross modeled card market value and C is the opening cost attached to the same run. A value of 0.5 means the modeled cards were worth half the opening cost. A value of 2 means twice the cost. This makes differently priced sets comparable without pretending raw dollars mean the same thing everywhere.</p>
    <p>The research tested several candidate bucket systems. V1 kept eight neutral ranges: 0–25%, 25–50%, 50–75%, 75–100%, 1–1.5×, 1.5–2×, 2–5×, and 5×+. That gave enough resolution around half-cost and break-even while preserving meaningful upside bands. A finer scheme created too many sparse cells; a simpler one hid too much of the middle. I also avoided labels like “terrible” or “great.” This is a descriptive distribution, not a verdict.</p>
    <LivePrismaticOutcomeProfile model={livePrismatic} />

    <H3>What the one-pack outcomes looked like</H3>
    <p>Across the frozen 22-set cohort, the mean probability of returning less than 25% of opening cost was 69.3%. The mean probability below half cost was 86.3%. Only 7.1% of openings, on average across sets, returned gross modeled card value equal to at least opening cost. The mean probabilities of returning at least 2× and 5× cost were 3.3% and 0.9%.</p>
    <p>“Returned at least cost” does not mean net profit. It means the modeled gross market value of cards met or exceeded the opening cost before fees, shipping, liquidity, condition, and the effort required to sell anything.</p>
    <OutcomeProbabilityFigure />
    <p>The contrasts matter. Prismatic Evolutions had more 5×+ tail probability than Journey Together, but far more openings below half cost. Temporal Forces had the strongest at-least-cost probability among these four examples. Phantasmal Flames had a large top-card EV contribution, yet relatively little 2×+ or 5×+ mass at its same-run cost. One average cannot expose all of those shapes.</p>

    <H2>Financial RIP already captures some of this</H2>
    <p>I tested whether I had merely rediscovered information already present in <Link href={ARTICLE_PATHS.financial}>Financial RIP</Link>. Representativeness horizons were moderately negatively associated with the score: Spearman ρ was approximately −0.597 for the ±20% horizon and −0.596 for the 80% EV Horizon. Top-1% outcome share was about −0.600. Financial RIP already recognizes part of distribution quality, but it does not fully subsume representativeness.</p>
    <p>The Outcome Profile overlap was stronger. Probability below half cost correlated with Financial RIP at −0.848. At-least-cost probability correlated at 0.762; 2×+ at 0.671; and 5×+ at 0.491. Some overlap is expected because Financial RIP already reads true-win and hard-loss behavior.</p>

    <H3>Why I did not create another score</H3>
    <p>That overlap made the product decision clearer, not harder. Adding the new probabilities directly into Financial RIP could count similar financial information twice. Wrapping them in a “Distribution Score” or “Consistency Score” would also erase the distinctions the research had just uncovered.</p>
    <DefinitionGrid columns="md:grid-cols-3" items={[
      ["Financial RIP", "Evaluative: How financially favorable is this opening profile?"],
      ["Outcome Profile", "Descriptive: Where do modeled openings actually land?"],
      ["EV Representativeness", "Statistical: How well does the long-run mean describe realistic finite samples?"],
    ]} />
    <p>They overlap. They are not the same thing. The evidence did not justify an EV Quality, Risk, Representativeness, Distribution, or Consistency score, so I did not invent one.</p>

    <H2>More packs do not always improve break-even odds</H2>
    <p>The multi-pack extension produced a result that feels backward at first: increasing quantity does not universally increase the probability of breaking even.</p>
    <p>If a set’s long-run EV is below opening cost, averaging more packs pulls the session toward a below-cost expectation. At the same time, diversification can remove some of the small-session chance that one exceptional hit carries the whole purchase above cost. Concentration becomes tighter, but it can tighten around a losing mean.</p>
    <p>This research used 25,000 seeded empirical sessions at 1, 6, 9, 11, 18, and 36 packs. It remains research-only and should not be confused with the exact one-pack public profile.</p>

    <H2>The next question takes time</H2>
    <p>The historical system now stores exact-run observations instead of recalculating the past with today’s prices. The recovered baseline contains 88 observations: 22 sets on August 17, 18, 20, and 22, 2026.</p>
    <p>Early rank stability was high. Day-over-day Spearman correlations ranged from about 0.973 to 0.999 for Typical Capture, 0.994 to 0.998 for top-1% contribution, and 0.970 to 0.994 for the 80% EV Horizon. Four dates are not enough for a major longitudinal conclusion. The project is intentionally collecting 60–90 days before considering temporal classifications.</p>
    <p>The hypothesis I am watching is that a set becoming more valuable does not necessarily make EV more representative. Tail-driven appreciation could raise EV because a few chase outcomes become more valuable: EV up, top-1% share up, Typical Capture flat or down, and convergence longer. Distributed appreciation could lift more of the middle: EV and Typical Capture up, middle recovery buckets improving, top-1% share flat or down, and convergence improving.</p>
    <p>Those are research hypotheses, not production labels. I want enough market regimes to test them before naming them on the site.</p>

    <H2>What users now see on inDex</H2>
    <p>The Full Simulation Report now moves from the complete Outcome Distribution to “What Happens When You Open a Pack?”, then to “How Closely Does EV Match Real Openings?”, and finally to the technical simulation statistics.</p>
    <p>The graph shows the full distribution. Outcome Profile translates it into understandable cost-relative probabilities. EV Representativeness explains whether the average resembles finite opening experience. Financial RIP evaluates the economic attractiveness of the broader profile elsewhere in the product.</p>
    <p>Those live panels above are the same ones I use on the set page, not screenshots or article-specific recreations. I did that deliberately. If I improve how I explain these distributions later, the article and the product should improve together instead of drifting into two different explanations of the same statistic.</p>
    <p>The set pages for <Link href={setHref("Prismatic Evolutions")}>Prismatic Evolutions</Link>, <Link href={setHref("Journey Together")}>Journey Together</Link>, and <Link href={setHref("Temporal Forces")}>Temporal Forces</Link> show current market-linked results. Those live values can move. Every empirical number in this article remains frozen to the August 22, 2026 study cohort.</p>

    <H2>What this does not mean</H2>
    <p>The limitations are part of the result. Hiding them would make the numbers look cleaner and the research worse.</p>
    <ul className="list-disc space-y-3 pl-5">
      <li>These are modeled openings, and they depend on the modeled pull-rate assumptions. A large simulation reduces sampling noise; it cannot repair a wrong input model.</li>
      <li>Market values change. This article freezes one market date so its conclusions do not drift, while current set pages remain live.</li>
      <li>One-pack values are gross modeled card market value. Selling fees, liquidity, slippage, shipping, grading cost, grading upside, and additional condition variation are excluded.</li>
      <li>Simulation accuracy and market-price accuracy are separate problems. Agreement inside the simulation does not prove that every price can be realized.</li>
      <li>Multi-pack resampling assumes independent draws from the empirical pack distribution. Real product collation or shared-source effects could violate that assumption.</li>
      <li>Multiple product SKUs from one set share the underlying set distribution. The 137 product rows in the broader research are not 137 independent set observations.</li>
      <li>Twenty-two sets are useful, but not a massive cross-sectional sample. Correlations are observational associations, not causal laws.</li>
      <li>Four dates provide only a preliminary temporal baseline. They do not establish long-run stability, seasonality, or a durable appreciation classification.</li>
      <li>A probability is not a guarantee about the next pack. A confirmed horizon is a statistical threshold under this model, not a recommendation to open that many packs.</li>
    </ul>
    <p>The practical conclusion is narrower and, I think, more useful: EV is mathematically correct, but the same EV can describe radically different opening experiences. Before opening, it helps to know where the median sits, how much value depends on the extreme tail, where outcomes land relative to cost, and how slowly realized averages may concentrate.</p>
    <p>I still use EV. I just stopped asking it to tell the whole story.</p>

    <H2>References</H2>
    <p>These sources support the statistical methods used here. None of the authors studied Pokémon cards; applying their methods to modeled pack-opening distributions is the work documented in this article.</p>
    <ReferenceList items={references} />
  </ArticleShell>;
}
