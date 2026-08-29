import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const source = fs.readFileSync(new URL("./pokemonCardDetailClient.js", import.meta.url), "utf8");
const slugifySource = fs.readFileSync(new URL("../../utils/slugify.js", import.meta.url), "utf8")
  .replace(/export function/g, "function");
const executableSource = source.replace(/^import \{ toSetSlug \} from "\.\.\/\.\.\/utils\/slugify\.js";\r?\n/m, "");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(`${slugifySource}\n${executableSource}`).toString("base64")}`;
const { buildPokemonCardDetailHref, buildPokemonCardHref, normalizePokemonCardDetail, resolvePokemonPublicSetSlug } = await import(moduleUrl);

test("canonical object route canonicalizes set identities and preserves the variant", () => {
  assert.equal(buildPokemonCardDetailHref({ setCanonicalKey: "set / one", canonicalCardId: "card / one", cardVariantId: "variant ? one" }), "/TCGs/Pokemon/Sets/set-one/Cards/card%20%2F%20one?variant=variant%20%3F%20one");
  assert.equal(buildPokemonCardDetailHref({ setCanonicalKey: "ascendedHeroes", canonicalCardId: "card" }), "/TCGs/Pokemon/Sets/ascended-heroes/Cards/card");
});

test("public set names are the primary route authority across eras", () => {
  assert.equal(resolvePokemonPublicSetSlug({ name: "Ascended Heroes", canonical_key: "ascendedHeroes" }), "ascended-heroes");
  assert.equal(resolvePokemonPublicSetSlug({ name: "Surging Sparks", slug: "surgingSparks" }), "surging-sparks");
  assert.equal(resolvePokemonPublicSetSlug({ name: "Paldea Evolved" }), "paldea-evolved");
  assert.equal(resolvePokemonPublicSetSlug({ name: "Neo Genesis" }), "neo-genesis");
});

test("unrelated sets and cards produce their own canonical destinations", () => {
  const cases = [
    ["Ascended Heroes", "card-ah"],
    ["Surging Sparks", "card-ss"],
    ["Paldea Evolved", "card-pe"],
    ["Neo Genesis", "card-ng"],
  ];
  const hrefs = cases.map(([setName, canonicalCardId]) => buildPokemonCardDetailHref({ setName, canonicalCardId }));
  assert.equal(new Set(hrefs).size, cases.length);
  assert.deepEqual(hrefs, [
    "/TCGs/Pokemon/Sets/ascended-heroes/Cards/card-ah",
    "/TCGs/Pokemon/Sets/surging-sparks/Cards/card-ss",
    "/TCGs/Pokemon/Sets/paldea-evolved/Cards/card-pe",
    "/TCGs/Pokemon/Sets/neo-genesis/Cards/card-ng",
  ]);
});

test("missing canonical card identity cannot create a route", () => {
  assert.equal(buildPokemonCardDetailHref({ setCanonicalKey: "set-one", cardVariantId: "variant-only" }), null);
});

test("different cards and variants preserve distinct destinations", () => {
  assert.notEqual(buildPokemonCardDetailHref({ setCanonicalKey: "set-one", canonicalCardId: "card-one", cardVariantId: "v1" }), buildPokemonCardDetailHref({ setCanonicalKey: "set-one", canonicalCardId: "card-two", cardVariantId: "v2" }));
  assert.equal(buildPokemonCardDetailHref({ setCanonicalKey: "set-one", canonicalCardId: "card-one", cardVariantId: "v3" }), "/TCGs/Pokemon/Sets/set-one/Cards/card-one?variant=v3");
});

test("card href uses canonical identity and preserves displayed variant", () => {
  assert.equal(
    buildPokemonCardHref("ascended-heroes", { id: "canonical", cardVariantId: "variant" }),
    "/TCGs/Pokemon/Sets/ascended-heroes/Cards/canonical?variant=variant"
  );
});

test("card href remains canonical when no variant exists", () => {
  assert.equal(
    buildPokemonCardHref("ascended-heroes", { canonicalCardId: "canonical" }),
    "/TCGs/Pokemon/Sets/ascended-heroes/Cards/canonical"
  );
});

test("similar card names never affect canonical route identity", () => {
  assert.equal(
    buildPokemonCardHref("pitch-black", { canonicalCardId: "gengar-002", cardName: "Gengar ex" }),
    "/TCGs/Pokemon/Sets/pitch-black/Cards/gengar-002"
  );
  assert.equal(
    buildPokemonCardHref("pitch-black", { canonicalCardId: "gengar-199", cardName: "Gengar ex" }),
    "/TCGs/Pokemon/Sets/pitch-black/Cards/gengar-199"
  );
});

test("normalizer preserves backend-authoritative selection and variants", () => {
  const payload = normalizePokemonCardDetail({
    set: { name: "Ascended Heroes", targetId: "ascendedHeroes", slug: "ascendedHeroes" },
    card: { id: "canonical" },
    availableVariants: [{ cardVariantId: "v1" }, { cardVariantId: "v2" }],
    selectedVariantId: "v2",
    variantSelection: { state: "selected", source: "query" },
    market: { currentPrice: 12 },
    chase: { available: true },
  });
  assert.equal(payload.selectedVariantId, "v2");
  assert.equal(payload.availableVariants.length, 2);
  assert.equal(payload.variantSelection.source, "query");
  assert.equal(payload.set.targetId, "ascendedHeroes");
  assert.equal(payload.set.slug, "ascended-heroes");
});
