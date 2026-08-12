import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relative) => fs.readFileSync(path.join(here, relative), "utf8").replace(/\r\n/g, "\n");

const hub = read("page.js");
const article = read("how-rip-score-works/page.js");
const header = read("../../components/Header.js");
const footer = read("../../components/Footer.jsx");
const bottomNav = read("../../components/GlobalMobileBottomNav.js");
const rip = read("../../components/explore/RipDecisionPage.jsx");
const methodologySection = read("../../components/landing/MethodologySection.jsx");
const nextConfig = read("../../next.config.mjs");

const ARTICLE_HREF = "/Articles/how-rip-score-works";

/* ------------------------------------------------------------------ *
 * The article — the migrated methodology content
 * ------------------------------------------------------------------ */

test("the RIP methodology article is a standalone page, never a set redirect", () => {
  assert.ok(article.includes("export default function HowRipScoreWorksArticle()"));
  assert.ok(/>\s*How the RIP Score Works\s*<\/h1>/.test(article), "the h1 names the article");
  assert.ok(!article.includes("redirect("));
  assert.ok(!article.includes("/Explore/rip-statistics"));
});

test("the article documents the canonical public methodology contracts", () => {
  for (const phrase of ["Overall RIP", "Financial RIP", "Collector Appeal", "True Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside Quality", "Base Economic Efficiency", "Roster desirability", "Desirable outcome frequency", "Dual-path depth", "P50", "P95", "P99", "eligible cohort", "official Pokémon pull rates", "one million", "TCGplayer", "unsupported", "transaction costs"]) {
    assert.ok(article.includes(phrase), phrase);
  }
  assert.ok(!article.includes("RIP Score</h2>"), "the retired metric label must not head a section");
  assert.ok(!article.includes("Realistic Upside"));
});

test("the article does not disclose production weights or scoring coefficients", () => {
  assert.ok(!/\b\d+(?:\.\d+)?%\s+(?:Financial RIP|Collector Appeal)/.test(article));
  assert.ok(!/\["[^"]+",\s*"\d+(?:\.\d+)?%"/.test(article));
  assert.ok(!article.includes("90% Financial RIP"));
  assert.ok(!article.includes("10% Collector Appeal"));
  assert.ok(!article.includes("weighted formula"));
});

/* ------------------------------------------------------------------ *
 * The hub
 * ------------------------------------------------------------------ */

test("the Articles hub lists only real, published articles", () => {
  assert.ok(hub.includes(`href: "${ARTICLE_HREF}"`), "the RIP methodology article is listed");

  const listed = [...hub.matchAll(/href: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(listed, [ARTICLE_HREF], "no unwritten article may be advertised on the hub");

  // A future topic must not ship as a dead card or a thin placeholder route.
  for (const unwritten of ["How Financial RIP Works", "How Collector Appeal Works", "Coming soon", "ComingSoonPage"]) {
    assert.ok(!hub.includes(unwritten), `${unwritten} must not appear until the article exists`);
  }
});

/* ------------------------------------------------------------------ *
 * Navigation — hub intent vs methodology intent
 * ------------------------------------------------------------------ */

test("global navigation points at the Articles hub", () => {
  assert.ok(header.includes('href="/Articles"'));
  assert.ok(header.includes(">\n                Articles"));
  assert.ok(footer.includes('{ label: "Articles", href: "/Articles" }'));
  assert.ok(bottomNav.includes('label: "Articles"'));
  assert.ok(bottomNav.includes('href: "/Articles"'));
});

test("methodology surfaces deep-link to the article, not to the hub", () => {
  assert.ok(rip.includes(`const METHODOLOGY_ARTICLE_HREF = "${ARTICLE_HREF}"`));
  assert.ok(rip.includes("methodologyHref = METHODOLOGY_ARTICLE_HREF"));
  assert.ok(methodologySection.includes(`methodologyHref = "${ARTICLE_HREF}"`));
});

test("no navigation surface still sends users to the retired Research route", () => {
  for (const [name, source] of [
    ["Header", header],
    ["Footer", footer],
    ["GlobalMobileBottomNav", bottomNav],
    ["RipDecisionPage", rip],
    ["MethodologySection", methodologySection],
    ["Articles hub", hub],
    ["RIP methodology article", article],
  ]) {
    assert.ok(!/["']\/[Rr]esearch["']/.test(source), `${name} must not link to the legacy Research route`);
  }
});

/* ------------------------------------------------------------------ *
 * Legacy route
 * ------------------------------------------------------------------ */

test("the legacy Research route is a permanent redirect to the article, not a duplicate page", () => {
  assert.ok(
    !fs.existsSync(path.join(here, "../Research")),
    "a live /Research page would be a second indexable copy of the article"
  );

  const entry = new RegExp(
    `source: "/Research",\\s*\\n\\s*destination: "${ARTICLE_HREF}",\\s*\\n\\s*permanent: true`
  );
  assert.ok(entry.test(nextConfig), `/Research must permanently redirect to ${ARTICLE_HREF}`);

  // Redirect `source` matching is case-insensitive, so /research is covered by
  // the rule above. The same property makes an /articles -> /Articles rule a
  // self-redirect loop on the canonical URL, which is why none exists.
  assert.ok(
    !/source: "\/articles"/.test(nextConfig),
    "a lowercase /articles rule would 308 the canonical /Articles to itself forever"
  );
});
