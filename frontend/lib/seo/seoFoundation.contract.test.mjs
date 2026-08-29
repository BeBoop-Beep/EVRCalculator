import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { buildRouteMetadata, NOINDEX_FOLLOW_ROBOTS, SITE_NAME } from "./routeMetadata.mjs";
import { buildRobotsPolicy } from "./robotsPolicy.mjs";
import { buildSitemapEntries } from "./sitemapEntries.mjs";
import { buildSiteStructuredData } from "./structuredData.mjs";
import { canonicalUrl, getCanonicalSiteOrigin, PRODUCTION_SITE_ORIGIN } from "./siteUrl.mjs";

/**
 * Fixture targets in the shape the canonical `/explore/rip-statistics/targets`
 * payload uses. `Sword & Shield` is present specifically because it is
 * public-analytics ineligible and must NOT reach the sitemap.
 */
const SITEMAP_FIXTURE_TARGETS = [
  { target_type: "set", target_id: "a", name: "Perfect Order", run_at: "2026-08-11T18:04:49.285676+00:00" },
  { target_type: "set", target_id: "b", name: "Scarlet and Violet 151", run_at: null },
  { target_type: "set", target_id: "c", name: "Sword & Shield", era: "Sword and Shield", run_at: "2026-08-11T18:04:49Z" },
  { target_type: "card", target_id: "d", name: "Some Card", run_at: "2026-08-11T18:04:49Z" },
  { target_type: "set", target_id: "e", name: "", run_at: "2026-08-11T18:04:49Z" },
];

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, "../../app");
const read = (relativePath) => fs.readFileSync(path.resolve(HERE, "../..", relativePath), "utf8");

// The canonical eligibility gate and slug function live in `.js` modules that
// this runner cannot `import` (they are resolved as CommonJS and expose no
// named ESM exports — the same limitation the slugify contract tests document).
// `createRequire` loads them properly, so the sitemap assertions below run
// against the REAL production helpers, not stand-ins.
const requireCjs = createRequire(import.meta.url);
const { isPublicAnalyticsEligiblePokemonSet } = requireCjs("../pokemon/pokemonSetPublicCoverage.js");
const { toSetSlug } = requireCjs("../../utils/slugify.js");

// ripStatisticsRouting.js imports through the "@/" bundler alias, which this
// runner cannot resolve. Loaded with the same source-splice + data-URL pattern
// ripStatisticsRouting.test.mjs already uses, so the assertions below run
// against the REAL alias map rather than against a copy of it.
const readText = (relativePath) =>
  fs.readFileSync(path.resolve(HERE, relativePath), "utf8").replace(/\r\n/g, "\n");
const slugifySource = readText("../../utils/slugify.js")
  .replace(/export function/g, "function")
  .replace(/\btoSetSlug\b/g, "toCanonicalSetSlug");
const routingSource = readText("../explore/ripStatisticsRouting.js").replace(
  /^import \{[^}]*\} from "@\/utils\/slugify";\n/m,
  ""
);
const { isLegacySetDetailTabAlias } = await import(
  `data:text/javascript;base64,${Buffer.from(`${slugifySource}\n${routingSource}`, "utf8").toString("base64")}`
);
const CANONICAL_SITEMAP_HELPERS = { isEligibleSet: isPublicAnalyticsEligiblePokemonSet, toSlug: toSetSlug };

/* ------------------------------------------------------------------ *
 * Canonical origin
 * ------------------------------------------------------------------ */

test("canonical URLs are built from the production origin, never from a runtime/localhost base", () => {
  assert.equal(getCanonicalSiteOrigin(), PRODUCTION_SITE_ORIGIN);
  assert.equal(canonicalUrl("/"), "https://www.inthedex.io/");
  assert.equal(canonicalUrl("/Rankings"), "https://www.inthedex.io/Rankings");
  assert.equal(canonicalUrl("/TCGs/Pokemon/Sets"), "https://www.inthedex.io/TCGs/Pokemon/Sets");
});

test("canonical URLs drop query strings, hashes and trailing slashes", () => {
  assert.equal(
    canonicalUrl("/TCGs/Pokemon/Sets/perfect-order?tab=cards&section=market-movers"),
    "https://www.inthedex.io/TCGs/Pokemon/Sets/perfect-order"
  );
  assert.equal(canonicalUrl("/Market#movers"), "https://www.inthedex.io/Market");
  assert.equal(canonicalUrl("/Articles/how-rip-score-works/"), "https://www.inthedex.io/Articles/how-rip-score-works");
});

/* ------------------------------------------------------------------ *
 * Route metadata builder
 * ------------------------------------------------------------------ */

test("buildRouteMetadata gives every route its OWN canonical and og:url", () => {
  const metadata = buildRouteMetadata({
    path: "/Market",
    title: "Pokémon Market Trends & Set Values — inDex",
    description: "Market movement.",
  });

  assert.equal(metadata.alternates.canonical, "https://www.inthedex.io/Market");
  assert.equal(metadata.openGraph.url, "https://www.inthedex.io/Market");
  assert.equal(metadata.openGraph.siteName, SITE_NAME);
  assert.equal(metadata.openGraph.title, metadata.title);
  assert.equal(metadata.twitter.title, metadata.title);
  assert.equal(metadata.twitter.description, metadata.description);
  assert.equal(metadata.twitter.card, "summary_large_image");
  // A route that says nothing about robots must not accidentally acquire a rule.
  assert.equal(metadata.robots, undefined);
});

test("social title/description can differ from the search title without desynchronising og and twitter", () => {
  const metadata = buildRouteMetadata({
    path: "/Rankings",
    title: "Search title",
    description: "Search description",
    ogTitle: "Social title",
    ogDescription: "Social description",
  });
  assert.equal(metadata.openGraph.title, "Social title");
  assert.equal(metadata.twitter.title, "Social title");
  assert.equal(metadata.openGraph.description, "Social description");
  assert.equal(metadata.twitter.description, "Social description");
});

test("NOINDEX_FOLLOW_ROBOTS keeps outbound links crawlable", () => {
  assert.equal(NOINDEX_FOLLOW_ROBOTS.index, false);
  assert.equal(NOINDEX_FOLLOW_ROBOTS.follow, true);
  assert.equal(NOINDEX_FOLLOW_ROBOTS.googleBot.index, false);
  assert.equal(NOINDEX_FOLLOW_ROBOTS.googleBot.follow, true);
});

/* ------------------------------------------------------------------ *
 * Root layout
 * ------------------------------------------------------------------ */

test("root layout sets metadataBase and no longer claims the homepage for every route", () => {
  const layout = read("app/layout.js");
  assert.ok(layout.includes("metadataBase: new URL(getCanonicalSiteOrigin())"));
  // The literal that made every page's og:url the homepage.
  assert.ok(
    !layout.includes('url: "https://www.inthedex.io/"'),
    "root openGraph must not hard-code an og:url that every route inherits"
  );
  assert.ok(
    !/alternates\s*:/.test(layout),
    "a canonical declared in the root layout would be inherited by every route"
  );
});

/* ------------------------------------------------------------------ *
 * Primary route canonicals
 * ------------------------------------------------------------------ */

const PRIMARY_ROUTES = [
  ["app/page.js", "/"],
  ["app/Rankings/page.js", "/Rankings"],
  ["app/Market/page.js", "/Market"],
  ["app/Articles/page.js", "/Articles"],
  ["app/Articles/how-rip-score-works/page.js", "/Articles/how-rip-score-works"],
  ["app/Articles/how-we-simulated-one-million-pokemon-pack-openings/page.js", "/Articles/how-we-simulated-one-million-pokemon-pack-openings"],
  ["app/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value/page.js", "/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value"],
  ["app/Articles/why-expected-value-alone-isnt-enough/page.js", "/Articles/why-expected-value-alone-isnt-enough"],
  ["app/Articles/how-financial-rip-works/page.js", "/Articles/how-financial-rip-works"],
  ["app/Articles/how-collector-appeal-works/page.js", "/Articles/how-collector-appeal-works"],
  ["app/Articles/how-representative-is-pokemon-pack-expected-value/page.js", "/Articles/how-representative-is-pokemon-pack-expected-value"],
  ["app/Articles/how-chase-efficiency-works/page.js", "/Articles/how-chase-efficiency-works"],
  ["app/TCGs/Pokemon/Sets/page.js", "/TCGs/Pokemon/Sets"],
];

for (const [relativePath, routePath] of PRIMARY_ROUTES) {
  test(`${routePath} declares its own canonical through the shared builder`, () => {
    const source = read(relativePath);
    assert.ok(source.includes("buildRouteMetadata"), `${relativePath} must use the shared metadata builder`);
    assert.ok(source.includes(`path: "${routePath}"`), `${relativePath} must canonicalise to ${routePath}`);
  });
}

test("the approved public titles are the ones shipped", () => {
  assert.ok(read("app/Rankings/page.js").includes("Best Pokémon Sets to Rip Right Now — inDex"));
  assert.ok(read("app/Market/page.js").includes("Pokémon Market Index, Trends & Set Values — inDex"));
  assert.ok(read("app/Articles/how-rip-score-works/page.js").includes("How the RIP Score Works"));
  assert.ok(read("app/Articles/page.js").includes("Articles | inDex"));
});

/* ------------------------------------------------------------------ *
 * Dynamic set metadata + canonical policy
 * ------------------------------------------------------------------ */

test("the set route resolves a real set name through the existing canonical helper", () => {
  const source = read("app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  assert.ok(source.includes("export async function generateMetadata"));
  assert.ok(source.includes("findTargetBySetSlug"), "set name must come from the canonical targets payload");
  assert.ok(
    source.includes("${setName} Overall RIP, Expected Value & Opening Analysis — inDex"),
    "set title must be generated from the real set name"
  );
  assert.ok(!source.includes("Perfect Order"), "no set name may be hard-coded into metadata");
  // Metadata must reuse the slim cached route directory, not introduce the
  // heavyweight canonical rankings cohort as a second data path.
  assert.ok(source.includes("getPokemonSetRouteDirectory({ limit: 150 })"));
  assert.ok(!source.includes("getRipStatisticsTargets"));
});

test("the set route canonicalises every query variant onto the bare set URL", () => {
  const source = read("app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  assert.ok(source.includes('buildTcgSetHrefFromTarget(selectedTarget).split("?")[0]'));
  assert.ok(source.includes("buildRouteMetadata({\n      path: canonicalPath") || source.includes("path: canonicalPath"));
});

test("legacy default-view tab aliases permanently redirect; ?tab=overview does not", () => {
  const source = read("middleware.js");

  // Middleware is the only layer that can still set a status code for this
  // route: the set page has a loading.js, so Next flushes the response shell
  // before the page component runs and a redirect thrown there degrades to a
  // client-side one.
  assert.ok(
    source.includes('isLegacySetDetailTabAlias(searchParams.get("tab"))'),
    "the alias list must come from the canonical routing helper, not be restated in middleware"
  );
  assert.ok(source.includes("NextResponse.redirect(url, 308)"), "the alias must collapse with a permanent redirect");
  assert.ok(source.includes('url.searchParams.delete("tab")'), "only the tab parameter is dropped");

  // The canonical helper decides what an alias is, and `overview` must not be
  // one — the client writes it on every RIP tab click.
  assert.equal(isLegacySetDetailTabAlias("rip"), true);
  assert.equal(isLegacySetDetailTabAlias("ANALYSIS"), true);
  assert.equal(isLegacySetDetailTabAlias("analytics"), true);
  assert.equal(isLegacySetDetailTabAlias("overview"), false);
  assert.equal(isLegacySetDetailTabAlias("market"), false);
  assert.equal(isLegacySetDetailTabAlias("cards"), false);
  assert.equal(isLegacySetDetailTabAlias(undefined), false);
  assert.ok(
    source.includes('"/TCGs/Pokemon/Sets/:setSlug*"'),
    "the set path must be in the middleware matcher or the redirect never runs"
  );

  // The route must still ALIAS them, so a request that bypasses middleware
  // renders the right tab instead of relying on the redirect.
  const route = read("app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  assert.ok(route.includes("resolveSetDetailTab(resolvedSearchParams?.tab)"));
  assert.ok(!route.includes("permanentRedirect"), "the route must not keep a redirect it cannot deliver");
});

/* ------------------------------------------------------------------ *
 * Legacy route policy
 * ------------------------------------------------------------------ */

test("thin/legacy routes are noindex, follow — not deleted, not indexable", () => {
  for (const relativePath of [
    "app/Explore/rip-statistics/page.js",
    "app/TCGs/page.js",
    "app/TCGs/Pokemon/page.js",
    "app/TCGs/Pokemon/Analytics/page.js",
  ]) {
    const source = read(relativePath);
    assert.ok(
      source.includes("export const metadata = { robots: NOINDEX_FOLLOW_ROBOTS };"),
      `${relativePath} must declare noindex, follow`
    );
  }
});

test("/Explore and /Explore/top-10 are permanent redirects, and top-10 no longer exists as a page", () => {
  const config = read("next.config.mjs");
  assert.ok(
    /source: "\/Explore",\s*destination: "\/Rankings",\s*permanent: true/.test(config),
    "the pre-existing /Explore -> /Rankings permanent redirect must be preserved"
  );
  assert.ok(
    /source: "\/Explore\/top-10",\s*destination: "\/Rankings",\s*permanent: true/.test(config)
  );
  assert.ok(
    !fs.existsSync(path.join(APP_DIR, "Explore", "top-10")),
    "the thin top-10 placeholder must not also exist as a 200 page"
  );
});

/* ------------------------------------------------------------------ *
 * Internal linking
 * ------------------------------------------------------------------ */

test("the set catalog links to the bare canonical set URL, not ?tab=cards", () => {
  const source = read("app/TCGs/Pokemon/Sets/page.js");
  assert.ok(
    source.includes("const setHref = slug ? `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}` : \"/TCGs/Pokemon/Sets\";")
  );
  // The prose above that line still names ?tab=cards to explain what changed,
  // so this asserts against the emitted href, not the file text.
  assert.ok(
    !/\$\{encodeURIComponent\(slug\)\}\?tab=/.test(source),
    "catalog links must not default to a query variant"
  );
});

/* ------------------------------------------------------------------ *
 * robots + sitemap
 * ------------------------------------------------------------------ */

test("robots exposes the sitemap and blocks only private/app-only families", () => {
  const result = buildRobotsPolicy();
  const rule = result.rules[0];

  assert.equal(rule.userAgent, "*");
  assert.equal(rule.allow, "/");
  assert.equal(result.sitemap, "https://www.inthedex.io/sitemap.xml");

  for (const publicPath of [
    "/Rankings",
    "/Market",
    "/Articles",
    "/Articles/how-rip-score-works",
    "/TCGs/Pokemon/Sets",
    "/cards",
    "/sealed-products",
    "/_next/",
    "/images/",
  ]) {
    assert.ok(
      !rule.disallow.some((entry) => publicPath.startsWith(entry)),
      `${publicPath} must remain crawlable`
    );
  }

  for (const privatePath of ["/api/", "/dashboard", "/my-collection", "/checkout"]) {
    assert.ok(rule.disallow.includes(privatePath), `${privatePath} should not be a public search destination`);
  }
});

test("the sitemap contains the canonical hubs and excludes redirects, noindex routes and query variants", () => {
  const entries = buildSitemapEntries(SITEMAP_FIXTURE_TARGETS, CANONICAL_SITEMAP_HELPERS);
  const urls = entries.map((entry) => entry.url);

  for (const hub of [
    "https://www.inthedex.io/",
    "https://www.inthedex.io/Rankings",
    "https://www.inthedex.io/Market",
    "https://www.inthedex.io/Articles",
    "https://www.inthedex.io/Articles/how-rip-score-works",
    "https://www.inthedex.io/Articles/how-representative-is-pokemon-pack-expected-value",
    "https://www.inthedex.io/Articles/how-chase-efficiency-works",
    "https://www.inthedex.io/TCGs/Pokemon/Sets",
  ]) {
    assert.ok(urls.includes(hub), `${hub} must be in the sitemap`);
  }

  assert.ok(!urls.some((url) => url.includes("/Explore")), "redirecting and noindex /Explore URLs must be excluded");
  assert.ok(!urls.some((url) => url.includes("/Analytics")), "noindex legacy routes must be excluded");
  assert.ok(!urls.some((url) => url.includes("?")), "no query variant may enter the sitemap");
  assert.equal(new Set(urls).size, urls.length, "sitemap URLs must be unique");

  // Hubs have no publication timestamp to reuse, so they must not invent one.
  const hubEntries = entries.filter((entry) => !entry.url.includes("/Sets/"));
  assert.ok(
    hubEntries.every((entry) => entry.lastModified === undefined),
    "lastModified must be omitted rather than stamped with the request time"
  );
});

test("the sitemap lists only eligible sets, by bare canonical URL, and omits unknown lastModified", () => {
  const entries = buildSitemapEntries(SITEMAP_FIXTURE_TARGETS, CANONICAL_SITEMAP_HELPERS);
  const setEntries = entries.filter((entry) => entry.url.includes("/Sets/"));

  assert.deepEqual(
    setEntries.map((entry) => entry.url),
    [
      "https://www.inthedex.io/TCGs/Pokemon/Sets/perfect-order",
      "https://www.inthedex.io/TCGs/Pokemon/Sets/scarlet-and-violet-151",
    ],
    "public-analytics-ineligible sets, non-set targets and unnamed rows must all be dropped"
  );

  const [perfectOrder, sv151] = setEntries;
  assert.ok(perfectOrder.lastModified instanceof Date, "a real run_at is reused as lastModified");
  assert.equal(perfectOrder.lastModified.toISOString(), new Date("2026-08-11T18:04:49.285676+00:00").toISOString());
  assert.equal(sv151.lastModified, undefined, "a missing run_at must omit lastModified, not invent one");
});

test("the sitemap projection never fabricates a lastModified", () => {
  const source = read("lib/seo/sitemapEntries.mjs");
  assert.ok(!/lastModified\s*:\s*new Date\(\)/.test(source));
  assert.ok(source.includes("toLastModified(target?.run_at)"));
});

test("a backend failure degrades the sitemap to the canonical hubs rather than erroring", () => {
  assert.deepEqual(
    buildSitemapEntries(null, CANONICAL_SITEMAP_HELPERS).map((entry) => entry.url),
    [
      "https://www.inthedex.io/",
      "https://www.inthedex.io/Rankings",
      "https://www.inthedex.io/Market",
      "https://www.inthedex.io/Articles",
      "https://www.inthedex.io/Articles/how-rip-score-works",
      "https://www.inthedex.io/Articles/how-we-simulated-one-million-pokemon-pack-openings",
      "https://www.inthedex.io/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value",
      "https://www.inthedex.io/Articles/why-expected-value-alone-isnt-enough",
      "https://www.inthedex.io/Articles/how-financial-rip-works",
      "https://www.inthedex.io/Articles/how-collector-appeal-works",
      "https://www.inthedex.io/Articles/how-representative-is-pokemon-pack-expected-value",
      "https://www.inthedex.io/Articles/how-chase-efficiency-works",
      "https://www.inthedex.io/TCGs/Pokemon/Sets",
    ]
  );
});

/* ------------------------------------------------------------------ *
 * Site entity (WebSite + Organization structured data)
 * ------------------------------------------------------------------ */

const siteGraph = buildSiteStructuredData();
const nodeOfType = (type) => siteGraph["@graph"].filter((node) => node["@type"] === type);

test("the site emits exactly one WebSite and one Organization, in one graph", () => {
  assert.equal(siteGraph["@context"], "https://schema.org");
  assert.equal(nodeOfType("WebSite").length, 1, "competing WebSite entities are competing site identities");
  assert.equal(nodeOfType("Organization").length, 1);
});

test("WebSite names the brand, its legitimate variants and the canonical origin", () => {
  const [website] = nodeOfType("WebSite");
  assert.equal(website.url, "https://www.inthedex.io/");
  assert.equal(website["@id"], "https://www.inthedex.io/#website");
  assert.equal(website.name, SITE_NAME);
  assert.equal(website.name, "inDex");
  // Asserted as an exact set, not a subset: a name added here is a new public
  // claim about what this entity is called, so it should have to be deliberate.
  assert.deepEqual(website.alternateName, ["inDex Pokémon", "inDex Pokémon TCG", "inthedex"]);
  assert.ok(
    !website.alternateName.includes("inthedex.io"),
    "a fully-qualified domain is an address, not an alternate name — `url` already states it"
  );
});

test("Organization shares the brand name and points at a logo asset that exists", () => {
  const [organization] = nodeOfType("Organization");
  assert.equal(organization["@id"], "https://www.inthedex.io/#organization");
  assert.equal(organization.name, SITE_NAME);
  assert.equal(organization.url, "https://www.inthedex.io/");
  assert.equal(organization.logo.url, "https://www.inthedex.io/icon-512.png");
  assert.ok(
    fs.existsSync(path.resolve(HERE, "../../public/icon-512.png")),
    "the declared logo must be a real public asset, not a promised one"
  );
});

test("Organization asserts nothing the repository cannot corroborate", () => {
  const [organization] = nodeOfType("Organization");
  for (const invented of ["sameAs", "address", "telephone", "founder", "legalName", "email"]) {
    assert.equal(organization[invented], undefined, `${invented} must not be invented`);
  }
});

test("the graph is connected rather than two unrelated fragments", () => {
  const [website] = nodeOfType("WebSite");
  const [organization] = nodeOfType("Organization");
  assert.equal(website.publisher["@id"], organization["@id"]);
});

test("the site entity associates inDex with the Pokemon TCG in plain language", () => {
  const [website] = nodeOfType("WebSite");
  assert.match(website.description, /Pok[eé]mon TCG/);
  assert.ok(website.description.startsWith("inDex is "));
});

test("the homepage is the one route that emits the site entity", () => {
  const home = read("app/page.js");
  assert.ok(home.includes("buildSiteStructuredData"));
  assert.ok(home.includes('type="application/ld+json"'));

  const layout = read("app/layout.js");
  assert.ok(
    !layout.includes("ld+json"),
    "site-level JSON-LD in the root layout would restate the site's url on every route"
  );

  for (const route of ["app/Rankings/page.js", "app/Market/page.js", "app/Articles/page.js"]) {
    assert.ok(!read(route).includes("buildSiteStructuredData"), `${route} must not emit a second site entity`);
  }
});

test("the JSON-LD payload survives serialization", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(siteGraph)), siteGraph);
});

/* ------------------------------------------------------------------ *
 * Account routes stay out of the index under BOTH spellings
 * ------------------------------------------------------------------ */

test("robots disallows the account collection under its public URL, not only its legacy one", () => {
  const rule = buildRobotsPolicy().rules[0];
  for (const accountPath of ["/my-collection", "/my-portfolio", "/my-portfolio/wishlist"]) {
    assert.ok(
      rule.disallow.some((entry) => accountPath.startsWith(entry)),
      `${accountPath} must be disallowed`
    );
  }
});
