import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const source = fs.readFileSync(new URL("./pokemonCardDetailClient.js", import.meta.url), "utf8");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const { buildPokemonCardHref, normalizePokemonCardDetail } = await import(moduleUrl);

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

test("normalizer preserves backend-authoritative selection and variants", () => {
  const payload = normalizePokemonCardDetail({
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
});
