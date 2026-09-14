import { ArticleJsonLd, ArticleShell, Citation, DefinitionGrid, H2, ReferenceList } from "@/components/articles/ArticlePrimitives";
import { ARTICLE_PATHS, articleByKey, related } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

const title = "How Chase Accessibility Works";
const description = "How inDex measures a set's modeled access to important collectible values, and why its raw metric, public score, and set rank mean different things.";
const registeredArticle = articleByKey("chaseAccessibility");
const references = [
  { id: "ref-openstax-probability", href: "https://openstax.org/books/introductory-statistics-2e/pages/3-introduction", citation: "OpenStax. Introductory Statistics 2e. Chapter 3: Probability Topics.", note: "Supports the general probability concepts used when modeled pack outcomes are combined." },
];

export const metadata = buildRouteMetadata({ path: "/Articles/how-chase-accessibility-works", title: "Pokémon Chase Accessibility Methodology | inDex", description, ogTitle: title });

export default function HowChaseAccessibilityWorksArticle() {
  return <ArticleShell category="Methodology" title={title} deck="Chase Accessibility asks how reachable a set's most important collectible values are from one modeled pack. It is a set-level RIP Score pillar, not the odds of one card." lastUpdated={registeredArticle.lastUpdated} related={related("rip", "collector", "financial", "chaseEfficiency")}>
    <ArticleJsonLd title={title} description={description} path={ARTICLE_PATHS.chaseAccessibility} lastUpdated={registeredArticle.lastUpdated} />
    <p>Choosing one highest-priced card would make the answer depend on an arbitrary cutoff. Chase Accessibility instead evaluates the important collectible value represented across a set. It uses modeled pack probabilities and places more significance on more important collectible values, so a set with meaningful access across its value structure can read differently from one dominated by a single remote hit.</p>
    <p>The pack probabilities come from the same modeled opening authority used by the set analysis. They remain model estimates, not guarantees. Missing probability coverage fails closed instead of being filled with a neutral score.</p>

    <H2>Raw measurement, public score, and rank</H2>
    <DefinitionGrid items={[
      ["Raw Accessibility", "The underlying modeled collectible-value accessibility measurement. It is not the probability of pulling ‘a chase.’"],
      ["Public score", "The comparative presentation of Raw Accessibility across the eligible set cohort."],
      ["Set rank", "The set's ordering inside that cohort, reported separately from both the raw measurement and public score."],
    ]} />
    <p>A public score of 6.4 / 10 does not mean a 64% chance of pulling a chase. Score formatting makes sets easier to compare; it does not turn the underlying measurement into literal pull odds.</p>

    <H2>Diagnostics and confidence</H2>
    <p>Chase Depth supplies diagnostic context about how the modeled important-value structure is distributed. It is not a literal count of chase cards and should not be read as one.</p>
    <p>Probability coverage, also reported as mapped HC mass, shows how much of the relevant modeled probability authority was successfully connected to the collectible-value calculation. Strong coverage increases confidence that the result represents the intended modeled pool. It does not prove real-world pull rates or make the next opening predictable.</p>

    <H2>What Chase Accessibility is not</H2>
    <DefinitionGrid items={[
      ["Top Chase odds", "The odds of one selected printing. Chase Accessibility considers the set's important collectible-value structure instead."],
      ["Product Chase", "A Premium, product-specific and budget-specific journey shown as Chase Access at $X. Chase Accessibility remains set-level and one-pack based."],
      ["Chase Efficiency", "A card-level comparison of pursuing one exact printing through verified opening routes versus its value."],
      ["Card market value", "Price is not sufficient by itself: modeled probability and the broader important-value structure matter too."],
    ]} />
    <p>Product Chase is deliberately separate. A booster pack, bundle, or box can inherit its parent set&apos;s Chase Accessibility while producing a different budget-specific Chase Access at $X journey.</p>

    <H2>Its role in RIP Score</H2>
    <p>RIP Score synthesizes Financial RIP, Chase Accessibility, and Collector Appeal as three peer pillars. Financial RIP asks how good the money outcomes are when opening the product. Chase Accessibility asks how reachable the parent set&apos;s important collectible values are. Collector Appeal describes how compelling the collectible roster is. Their peer presentation does not imply equal model weighting, and the exact model weights and transform constants are not published.</p>

    <H2>References</H2>
    <p>Chase Accessibility is original inDex methodology. The reference supports general probability language used in this explanation; it does not propose or independently validate the metric. See <Citation href="https://openstax.org/books/introductory-statistics-2e/pages/3-introduction">OpenStax</Citation> for the underlying probability concepts.</p>
    <ReferenceList items={references} />
  </ArticleShell>;
}
