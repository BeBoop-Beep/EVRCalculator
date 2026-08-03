import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

function read(relativePath) {
  return fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");
}

/** Assertions about what the code DOES must not be satisfied — or defeated — by
 *  what a comment above it happens to say. */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** JSX wraps prose across lines; compare the rendered text, not the source
 *  line breaks. */
function flatten(source) {
  return source.replace(/\s+/g, " ");
}

/** Everything after the imports — so an import name cannot stand in for a
 *  rendered element when asserting document order. */
function body(source) {
  const firstJsx = source.indexOf("return (");
  return firstJsx === -1 ? source : source.slice(firstJsx);
}

const page = read("../../app/page.js");
const hero = read("./LandingHero.jsx");
const heroCss = read("./LandingHero.module.css");
const showcase = read("./HeroShowcase.jsx");
const strip = read("./MarketStrip.jsx");
const levels = read("./LevelsSection.jsx");
const setSection = read("./SetIntelligenceSection.jsx");
const exploreSection = read("./ExploreSection.jsx");
const methodology = read("./MethodologySection.jsx");
const finalCta = read("./FinalCtaSection.jsx");
const layout = read("../../app/layout.js");
const landingCss = read("./landing.module.css");

const allCopy = [hero, showcase, strip, levels, setSection, exploreSection, methodology, finalCta].join("\n");

test("the seven bands render in order, once each, above the footer", () => {
  const order = [
    "<LandingHero",
    "<MarketStrip",
    "<LevelsSection",
    "<SetIntelligenceSection",
    "<ExploreSection",
    "<MethodologySection",
    "<FinalCtaSection",
    "<Footer",
  ];

  let cursor = -1;
  for (const marker of order) {
    const index = page.indexOf(marker, cursor + 1);
    assert.ok(index > cursor, `${marker} must follow the band before it`);
    cursor = index;
  }
});

test("the page states the Pokemon category before anything else", () => {
  assert.ok(
    hero.includes("Pokémon TCG market intelligence"),
    "the hero eyebrow names the category outright"
  );
  const heroBody = body(hero);
  const eyebrowAt = heroBody.indexOf("Pokémon TCG market intelligence");
  const headlineAt = heroBody.indexOf("<h1");
  assert.ok(eyebrowAt > -1 && headlineAt > -1);
  assert.ok(eyebrowAt < headlineAt, "the category line precedes the headline in the document");

  assert.ok(
    heroCss.includes("text-transform: uppercase") && heroCss.includes(".eyebrow"),
    "the category line is set as an uppercase eyebrow"
  );
});

test("the oversized inDex wordmark is gone from the hero", () => {
  assert.ok(!hero.includes("inDex_wm.png"), "the hero no longer repeats the wordmark the header carries");
  assert.ok(!heroCss.includes(".wordmark"), "and its geometry rules are removed with it");
  assert.ok(
    !hero.includes("markCrisp") && !hero.includes("markTint"),
    "the giant cropped mark silhouette is removed; only the glow remains"
  );
  assert.ok(heroCss.includes(".markGlow"), "the mark survives as the scene's light source");
});

test("the retained headline and the approved supporting copy are exact", () => {
  assert.ok(hero.includes("Know what&rsquo;s"), "the headline is retained verbatim");
  assert.ok(hero.includes("worth opening"));
  assert.ok(hero.includes("before you rip."));
  assert.ok(
    hero.includes("Live Pokémon set values, opening simulations, chase-card movement, and cross-set"),
    "the supporting hero copy is the approved line and keeps 'Pokémon'"
  );
});

test("Explore is the primary action and the waitlist is tertiary", () => {
  const heroBody = body(hero);
  assert.ok(hero.includes("Explore Pokémon sets"), "the yellow action is Explore");
  assert.ok(
    heroBody.indexOf("styles.ctaPrimary") < heroBody.indexOf("<WaitlistCta"),
    "Explore precedes the waitlist in the hero"
  );
  assert.ok(hero.includes("How RIP Score works"), "the secondary action is the methodology link");
  assert.ok(
    hero.includes('label="Join the portfolio waitlist"') && hero.includes('variant="link"'),
    "the waitlist is scoped to the portfolio product and rendered at link weight"
  );
  assert.ok(
    !/Join the waitlist/.test(allCopy),
    "the generic 'Join the waitlist' must not remain as a dominant action label"
  );
  assert.ok(
    finalCta.includes("styles.finalPrimary") && finalCta.includes("Explore Pokémon sets"),
    "the final CTA leads with Explore too"
  );

  const waitlist = read("./WaitlistDialog.jsx");
  assert.ok(
    waitlist.includes("submitWaitlistSignup") && waitlist.includes("Resend verification email"),
    "the waitlist behaviour itself is untouched"
  );
});

test("each required heading is present", () => {
  assert.ok(levels.includes("One pack. One set. The whole Pokémon market."));
  assert.ok(setSection.includes("Understand the set, not just the chase card."));
  assert.ok(exploreSection.includes("See where every tracked Pokémon set stands."));
  assert.ok(methodology.includes("Built from market data. Tested through simulation."));
  assert.ok(finalCta.includes("Market intelligence for every collecting decision."));
});

test("the three levels are questions, and none of them share a composition", () => {
  for (const question of ["Should I open it?", "What is driving the set?", "How does it compare?"]) {
    assert.ok(levels.includes(question), `${question} must be the level's heading`);
  }
  for (const label of ["RIP Score", "Set Intelligence", "Explore"]) {
    assert.ok(levels.includes(label));
  }
  assert.ok(
    levels.includes("levelCardSealed") && levels.includes("levelCardCards") && levels.includes("levelCardBoard"),
    "each level gets its own composition class, not one card design repeated"
  );
});

test("real Pokemon product imagery carries the category, with a stated fallback ladder", () => {
  assert.ok(showcase.includes("<ChaseCardRow"), "the hero shows real chase-card art");
  assert.ok(
    /unavailable/i.test(showcase) && /fallback ladder/i.test(showcase),
    "the missing sealed imagery and the ladder around it are documented in the component"
  );

  const chaseCard = read("./previews/ChaseCard.jsx");
  const remoteImg = read("./previews/RemoteImg.jsx");
  assert.ok(remoteImg.includes("onError"), "a failed remote image falls back rather than breaking");
  assert.ok(
    chaseCard.includes("loading={priority ? \"eager\" : \"lazy\"}"),
    "below-the-fold card art is lazy-loaded"
  );
  // Every third-party image on the page must go through the fallback wrapper —
  // a raw <img> here is a broken-image glyph waiting to ship.
  for (const file of ["./MarketStrip.jsx", "./ExploreSection.jsx", "./previews/ChaseCard.jsx", "./previews/previewPrimitives.jsx"]) {
    assert.ok(!/<img\b/.test(read(file)), `${file} must render remote art through RemoteImg`);
  }
  assert.ok(
    landingCss.includes("aspect-ratio: var(--card-ratio)"),
    "card frames reserve their aspect ratio so late art cannot shift the layout"
  );

  const row = read("./previews/ChaseCardRow.jsx");
  assert.ok(row.includes("if (cards.length === 0) return null"), "no empty card frames render");
});

test("RIP Score is not left as an unexplained number", () => {
  const panel = read("./previews/FeaturedSetPanel.jsx");
  assert.ok(panel.includes("Opening profile"), "the panel leads with a readable rank");
  assert.ok(
    panel.indexOf("openingRank") < panel.indexOf("RIP Score"),
    "the rank precedes the score in the panel"
  );
  assert.ok(
    panel.includes("Relative opening rank&mdash;not a profit probability."),
    "the microcopy states what the score is not"
  );
  assert.ok(
    !/\bprobability of profit\b/i.test(allCopy),
    "RIP Score must never be described as a probability"
  );
});

test("no unsupported claim and no investment-advice language ships", () => {
  const forbidden = [
    "nobody else",
    "the only pokémon",
    "the only pokemon",
    "only platform",
    "guaranteed",
    "best investment",
    "will profit",
    "risk-free",
  ];
  const lowered = allCopy.toLowerCase();
  for (const phrase of forbidden) {
    assert.ok(!lowered.includes(phrase), `"${phrase}" must not appear in landing copy`);
  }
  assert.ok(methodology.includes("not financial advice"));
  assert.ok(
    flatten(finalCta).includes("as inDex expands"),
    "the portfolio product is described as forthcoming, never as available"
  );
});

test("the page reads its data once and every section is a server component", () => {
  assert.ok(page.includes("await getLandingPageData()"));
  assert.equal(
    (page.match(/await /g) || []).length,
    1,
    "no section may introduce a second awaited request on the homepage"
  );
  for (const section of [showcase, strip, levels, setSection, exploreSection, methodology, finalCta]) {
    assert.ok(!/\bfetch\(/.test(section), "sections receive data, they do not fetch it");
    assert.ok(!section.includes('"use client"'), "sections stay server components");
  }
});

test("the market strip is real published data, not a carousel", () => {
  assert.ok(strip.includes("Live Pokémon market"), "the strip is labelled");
  assert.ok(
    !/setInterval|setTimeout|autoplay|useEmbla|swiper/i.test(stripComments(strip)),
    "nothing on the strip auto-advances or hides behind a swipe"
  );
  assert.ok(
    /\.stripList\s*\{[^}]*display:\s*grid/.test(landingCss) &&
      !/\.stripList\s*\{[^}]*overflow-x:\s*auto/.test(landingCss),
    "the strip is a wrapping grid, never a horizontal scroller"
  );
  assert.ok(strip.includes("if (signals.length === 0) return null"), "an empty strip renders nothing");
});

test("no rigid viewport heights or spacer padding remain", () => {
  for (const [name, css] of [["hero", stripComments(heroCss)], ["sections", stripComments(landingCss)]]) {
    assert.ok(!/height:\s*100vh/.test(css), `${name}: no viewport-locked height`);
    assert.ok(!/\d+svh/.test(css), `${name}: no viewport-derived height math`);
    assert.ok(!/min-height:\s*clamp\(/.test(css), `${name}: no clamped viewport height`);
  }
  // The only min-heights left anywhere are touch targets — the hero frame is
  // sized by its content, which is what removed the empty band beside the copy.
  for (const [name, css] of [["hero", stripComments(heroCss)], ["sections", stripComments(landingCss)]]) {
    const minHeights = [...new Set([...css.matchAll(/min-height:\s*([^;]+);/g)].map((m) => m[1].trim()))];
    for (const value of minHeights) {
      assert.match(
        value,
        /^(4[4-9]|5\d|6\d|7[0-6])px$/,
        `${name}: min-height ${value} is not a touch target — no element may reserve empty height`
      );
    }
  }
});

test("the mobile hero is recomposed rather than scaled", () => {
  const mobileBlock = heroCss.slice(heroCss.indexOf("@media (max-width: 960px)"));
  assert.ok(mobileBlock.includes("background: none"), "the frame's card chrome comes off on phones");
  assert.ok(
    !/transform:\s*scale\(/.test(mobileBlock),
    "the mobile hero must not be a scaled copy of the desktop one"
  );
  assert.ok(!/zoom:/.test(heroCss));
  assert.ok(!/transform:\s*scale\(/.test(landingCss), "no section below the hero is scaled either");
});

test("nothing on the page is trapped behind the fixed bottom navigation", () => {
  assert.ok(
    layout.includes("pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0"),
    "the root layout keeps the page clear of the fixed mobile nav, safe area included"
  );
  assert.ok(
    !/position:\s*fixed/.test(landingCss),
    "no landing section may pin itself over the bottom navigation"
  );
});

test("the dialog is portalled out of the animated hero subtree", () => {
  const cta = read("./WaitlistCta.jsx");
  assert.ok(
    cta.includes("createPortal(<WaitlistDialog"),
    "the overlay must not resolve position:fixed against the hero's animated container"
  );
});

test("motion and focus floors hold", () => {
  for (const [name, css] of [["hero", heroCss], ["sections", landingCss]]) {
    assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"), `${name} respects reduced motion`);
    assert.ok(css.includes(":focus-visible"), `${name} keeps a visible focus treatment`);
  }
});

test("no sample financial value is hardcoded into a component", () => {
  for (const source of [showcase, strip, levels, setSection, exploreSection, methodology, finalCta]) {
    assert.ok(
      !/\$\s?\d/.test(source),
      "every currency figure must come from formatted published data, never a literal"
    );
  }
});
