import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const read = relative => fs.readFileSync(path.join(here, relative), "utf8").replace(/\r\n/g, "\n");
const hub = read("page.js");
const article = read("how-rip-score-works/page.js");
const articleData = read("../../lib/articles/articleData.mjs");
const rip = read("../../components/explore/RipDecisionPage.jsx");
const nextConfig = read("../../next.config.mjs");
const ARTICLE_HREF = "/Articles/how-rip-score-works";

test("the RIP methodology article is a standalone shared-layout article", () => {
  assert.ok(article.includes("export default async function HowRipScoreWorksArticle()"));
  assert.ok(article.includes('const title = "How the RIP Score Works"'));
  assert.ok(article.includes("<ArticleShell"));
  assert.ok(!article.includes("redirect("));
});
test("the article documents the current canonical methodology without protected weights", () => {
  for (const phrase of ["Overall RIP V8", "Financial RIP V3", "Collector Appeal V4", "True Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside Quality", "Base Economic Efficiency", "Roster Desirability", "Desirable Outcome Frequency", "Dual-Path Depth", "P50", "P95", "P99", "one million", "unsupported", "seller fees"]) assert.ok(article.includes(phrase), phrase);
  assert.ok(!article.includes("90% Financial RIP"));
  assert.ok(!article.includes("10% Collector Appeal"));
});
test("the Articles hub lists exactly six real published article routes", () => {
  assert.ok(hub.includes('import { ARTICLES }'));
  const listed = [...articleData.matchAll(/\w+: "(\/Articles\/[^"]+)"/g)].map(match => match[1]);
  assert.equal(listed.length, 6);
  for (const href of listed) assert.ok(fs.existsSync(path.join(here, href.replace("/Articles/", ""), "page.js")), href);
});
<<<<<<< HEAD
=======
test("the EV representativeness research article is fully registered", () => {
  const research = read("how-representative-is-pokemon-pack-expected-value/page.js");
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
>>>>>>> 867f66f (docs(articles): refine EV research article title)
test("methodology links route to the most relevant published article", () => {
  assert.ok(rip.includes(`const METHODOLOGY_ARTICLE_HREF = "${ARTICLE_HREF}"`));
  assert.ok(rip.includes('methodologyHref: "/Articles/how-financial-rip-works"'));
  assert.ok(rip.includes('methodologyHref: "/Articles/how-collector-appeal-works"'));
});
test("the legacy Research route permanently redirects to the canonical RIP article", () => {
  assert.match(nextConfig, new RegExp(`source: "/Research",\\s*\\n\\s*destination: "${ARTICLE_HREF}",\\s*\\n\\s*permanent: true`));
});
