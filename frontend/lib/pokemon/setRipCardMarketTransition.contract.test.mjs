import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (file) => fs.readFileSync(path.resolve(file), "utf8");
const rip = read("components/explore/RipDecisionPage.jsx");
const page = read("components/explore/RipStatisticsPageClient.jsx");
const snapshots = read("lib/pokemon/pokemonSetInitialSnapshotsServer.js");

test("RIP Top Chase uses one canonical Card Detail href for image, name, and CTA", () => {
  assert.match(rip, /canonicalCardId: chase\.canonicalCardId,/);
  assert.doesNotMatch(rip, /chase\.canonicalCardId \|\| chase\.cardId/);
  assert.ok((rip.match(/<Link href=\{cardHref\}/g) || []).length >= 3);
});

test("Market destination seeds are explicit, independently seeded, and suppress fallbacks while pending", () => {
  assert.match(snapshots, /resolvedTab,/);
  assert.match(snapshots, /marketMoversPayload: marketMovers\.payload/);
  assert.match(snapshots, /snapshot_contract", "pricing-v4"/);
  assert.match(page, /initialModuleSnapshots\?\.resolvedTab !== "market"/);
  assert.ok((page.match(/if \(destinationSeedPending\) return undefined;/g) || []).length >= 3);
  assert.ok(
    page.indexOf("const [setDetailTab, setSetDetailTab]") < page.indexOf("const destinationSeedPending"),
    "destination seed state must be derived only after the tab state hook initializes",
  );
});

test("Market bootstrap owns Standard history and Movers hydrate from prop updates", () => {
  assert.match(page, /const setValue = overviewSource/);
  assert.match(page, /overviewPayload: initialOverviewPayload/);
  assert.match(page, /dispatchMarketMovers\(\{[\s\S]*seededMarketMoversPayload/);
  const reducerStart = page.indexOf("const [marketMoversState, dispatchMarketMovers]");
  const reducerSource = page.slice(reducerStart, reducerStart + 500);
  assert.match(reducerSource, /status: seededMarketMoversPayload \? "success" : "idle"/);
  assert.match(reducerSource, /payload: seededMarketMoversPayload \|\| null/);
});

test("Cards intent timer is owned, replaced, cancelled on Market selection, and cleared on cleanup", () => {
  assert.match(page, /const cardsIntentPrefetchTimerRef = useRef\(null\)/);
  assert.match(page, /normalizedTab !== "cards" && cardsIntentPrefetchTimerRef\.current !== null/);
  assert.match(page, /window\.clearTimeout\(cardsIntentPrefetchTimerRef\.current\)/);
  assert.match(page, /cardsIntentPrefetchTimerRef\.current = window\.setTimeout/);
  assert.match(page, /cardsIntentPrefetchTimerRef\.current = null;[\s\S]{0,100}prefetchPokemonSetCardsPage/);
  assert.match(page, /useEffect\(\(\) => \(\) => \{/);
});

test("primary tabs use bounded auto scroll and sealed warming reuses the consumer cache", () => {
  assert.match(page, /attempts < 12/);
  assert.match(page, /getSetDetailFallbackTargetId\(normalizedTab\), "auto"/);
  assert.match(page, /requestIdleCallback\(warm, \{ timeout: 1500 \}\)/);
  assert.match(page, /navigator\?\.connection\?\.saveData === true/);
  assert.match(page, /getPokemonSetConsumerSealedMarket\(resolvedSetResourceId\)/);
});
