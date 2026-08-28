import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { ARTICLES } from "../../lib/articles/articleData.mjs";
const here = path.dirname(fileURLToPath(import.meta.url));
const read = relative => fs.readFileSync(path.join(here, relative), "utf8").replace(/\r\n/g, "\n");
const hub = read("page.js");
const article = read("how-rip-score-works/page.js");
const articleData = read("../../lib/articles/articleData.mjs");
const rip = read("../../components/explore/RipDecisionPage.jsx");
const nextConfig = read("../../next.config.mjs");
const ARTICLE_HREF = "/Articles/how-rip-score-works";
const chase = read("how-chase-efficiency-works/page.js");
const primitives = read("../../components/articles/ArticlePrimitives.jsx");
const financial = read("how-financial-rip-works/page.js");
const collector = read("how-collector-appeal-works/page.js");
const research = read("how-representative-is-pokemon-pack-expected-value/page.js");

test("the RIP methodology article is a standalone shared-layout article", () => {
  assert.ok(article.includes("export default async function HowRipScoreWorksArticle()"));
  assert.ok(article.includes('const title = "How the RIP Score Works"'));
  assert.ok(article.includes("<ArticleShell"));
  assert.ok(!article.includes("redirect("));
});
test("the article documents the current canonical methodology without protected weights", () => {
  for (const phrase of ["Overall RIP V10", "Public RIP Contract V10", "Financial RIP V4", "Collector Appeal V5", "0–10 RIP score", "displayed 10.0", "True Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside Quality", "Base Economic Efficiency", "Desirable Outcome Frequency", "Dual-Path Depth", "P50", "P95", "P99", "one million", "unsupported", "seller fees"]) assert.ok(article.includes(phrase), phrase);
  assert.ok(!article.includes("current canonical score is Overall RIP V8"));
  assert.ok(!article.includes("combines Financial RIP V3"));
  assert.ok(!article.includes("Collector Appeal V4 uses"));
  assert.ok(!article.includes("90% Financial RIP"));
  assert.ok(!article.includes("10% Collector Appeal"));
});
test("the Articles hub lists exactly eight real published article routes", () => {
  assert.ok(hub.includes('import { ARTICLES }'));
  const listed = [...articleData.matchAll(/\w+: "(\/Articles\/[^"]+)"/g)].map(match => match[1]);
  assert.equal(listed.length, 8);
  for (const href of listed) assert.ok(fs.existsSync(path.join(here, href.replace("/Articles/", ""), "page.js")), href);
});
test("every registered article has one shared modification date wired to its page", () => {
  assert.equal(ARTICLES.length, 8);
  for (const registered of ARTICLES) {
    assert.match(registered.lastUpdated, /^\d{4}-\d{2}-\d{2}$/);
    assert.equal(registered.lastUpdated, "2026-08-28");
    const page = read(`${registered.href.replace("/Articles/", "")}/page.js`);
    assert.ok(page.includes(`articleByKey("${registered.key}")`), registered.key);
    assert.ok(page.includes("lastUpdated={registeredArticle.lastUpdated}"), registered.key);
  }
});
test("every published article ends with meaningful references using the shared citation system", () => {
  for (const registered of ARTICLES) {
    const page = read(`${registered.href.replace("/Articles/", "")}/page.js`);
    assert.ok(page.includes("<H2>References</H2>"), registered.key);
    assert.ok(page.includes("ReferenceList"), registered.key);
    assert.ok(page.includes("<ReferenceList items={references} />"), registered.key);
    assert.match(page, /const references = \[[\s\S]*?id: "ref-/, registered.key);
    assert.ok(!page.includes("example.com"), registered.key);
    assert.ok(!/TODO[: ]+citation/i.test(page), registered.key);
  }
  assert.ok(primitives.includes('target="_blank"'));
  assert.ok(primitives.includes('rel="noreferrer"'));
});
test("the shared article header and JSON-LD expose dateModified without inventing publication dates", () => {
  assert.ok(primitives.includes("<time dateTime={lastUpdated}"));
  assert.ok(primitives.includes("Last updated {formatLastUpdated(lastUpdated)}"));
  assert.ok(primitives.includes('timeZone: "UTC"'));
  assert.ok(primitives.includes("dateModified: lastUpdated"));
  assert.ok(!primitives.includes("datePublished"));
});
test("Financial RIP and Collector Appeal describe the current scoring inputs", () => {
  assert.ok(financial.includes("Financial RIP V4"));
  assert.ok(financial.includes("P95 threshold relative to cost"));
  assert.ok(financial.includes("no longer contributes to the V4 score"));
  assert.ok(!financial.includes("It reads both that threshold and the conditional mean"));
  assert.ok(collector.includes("Collector Appeal V5"));
  assert.ok(collector.includes("same-run card EV contribution"));
  assert.ok(collector.includes("not a V5 score input"));
  assert.ok(collector.includes("separately visible diagnostic"));
});
test("the frozen EV study keeps its historical Financial RIP V3 context", () => {
  assert.ok(research.includes("These frozen comparisons use Financial RIP V3"));
  assert.ok(research.includes("August 22, 2026 study cohort"));
  assert.ok(research.includes("current production model has since advanced to Financial RIP V4"));
});
test("the Chase Efficiency methodology article is public without exposing Premium rows", () => {
  assert.ok(articleData.includes('chaseEfficiency: "/Articles/how-chase-efficiency-works"'));
  assert.ok(chase.includes("<ArticleShell"));
  assert.ok(chase.includes("<ArticleJsonLd"));
  for (const phrase of ["Chase Efficiency", "exact printing", "best verified", "Financial RIP", "Product Chase Economics", "50%", "75%", "90%", "95%", "4,862", "22", "17"]) assert.ok(chase.includes(phrase), phrase);
  for (const phrase of ["ref-tcgplayer-market-price", "ref-openstax-geometric", "original inDex methodology", "Source: inDex Chase Efficiency production publication", "August 27, 2026"]) assert.ok(chase.includes(phrase), phrase);
  assert.ok(!chase.includes("/api/explore/card-chase-efficiency"));
  assert.ok(!chase.includes("getPokemonCardChaseEfficiency"));
  assert.ok(!chase.includes("Top 10"));
  assert.ok(!chase.includes("Top 100"));
  const sitemap = read("../../lib/seo/sitemapEntries.mjs");
  assert.ok(sitemap.includes('"/Articles/how-chase-efficiency-works"'));
});
test("the EV representativeness research article is fully registered", () => {
  const editorialTitle = "How Well Does Expected Value Describe a Pokémon Pack Opening?";
  assert.ok(articleData.includes('evRepresentativeness: "/Articles/how-representative-is-pokemon-pack-expected-value"'));
  assert.ok(articleData.includes(`title: "${editorialTitle}"`));
  assert.ok(research.includes(`const title = "${editorialTitle}"`));
  assert.ok(research.includes('title: "Pokémon Pack Expected Value vs Real Outcomes: 22 Million Simulations | inDex"'));
  assert.ok(articleData.includes("22 million modeled pack outcomes"));
  assert.ok(research.includes("<ArticleJsonLd"));
  assert.ok(research.includes("<H2>References</H2>"));
  for (const doi of ["10.1080/01621459.1949.10483310", "10.1080/01621459.1927.10502953", "10.1214/aos/1176344552", "10.2307/1412159", "10.1111/j.2517-6161.1995.tb02031.x", "10.1007/978-0-387-21617-1"]) assert.ok(research.includes(doi), doi);
  for (const key of ['"ev"', '"simulation"', '"validation"', '"financial"']) assert.ok(research.includes(key), key);
});
test("the research article embeds live evidence through shared product components", () => {
  const page = read("how-representative-is-pokemon-pack-expected-value/page.js");
  const wrapper = read("../../components/articles/EvResearchLiveExamples.jsx");
  assert.ok(page.includes("<LivePrismaticDistribution"));
  assert.ok(page.includes("<LivePrismaticOutcomeProfile"));
  assert.ok(page.includes("<LivePrismaticEvRepresentativeness"));
  assert.ok(wrapper.includes("OpeningOutcomeProfileSection"));
  assert.ok(wrapper.includes("EvRepresentativenessSection"));
  assert.ok(wrapper.includes("LiveDistributionFigure"));
  assert.ok(wrapper.includes("same RipDistributionChart as the set page"));
});
test("methodology links route to the most relevant published article", () => {
  assert.ok(rip.includes(`const METHODOLOGY_ARTICLE_HREF = "${ARTICLE_HREF}"`));
  assert.ok(rip.includes('href: "/Articles/how-financial-rip-works"'));
  assert.ok(rip.includes('href: "/Articles/how-collector-appeal-works"'));
});
test("the legacy Research route permanently redirects to the canonical RIP article", () => {
  assert.match(nextConfig, new RegExp(`source: "/Research",\\s*\\n\\s*destination: "${ARTICLE_HREF}",\\s*\\n\\s*permanent: true`));
});
