import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  isOptimizableImageSource,
  optimizedImageSrcSet,
  optimizedImageUrl,
  snapImageWidth,
} from "./remoteImageDelivery.mjs";

const CARD = "https://images.pokemontcg.io/sv2/1.png";

test("optimizable hosts are routed through the Next image optimizer", () => {
  assert.equal(
    optimizedImageUrl(CARD, 256),
    "/_next/image?url=https%3A%2F%2Fimages.pokemontcg.io%2Fsv2%2F1.png&w=256&q=75",
  );
  assert.equal(
    optimizedImageUrl("https://images.scrydex.com/pokemon/me4-logo/logo", 384),
    "/_next/image?url=https%3A%2F%2Fimages.scrydex.com%2Fpokemon%2Fme4-logo%2Flogo&w=384&q=75",
  );
});

test("sources this origin cannot optimize are returned untouched", () => {
  // Anything not covered by `images.remotePatterns` would 400 through the
  // optimizer, so these must keep rendering exactly as they do today.
  for (const src of [
    "/images/inDex.png",
    "https://example.invalid/card.png",
    "http://images.pokemontcg.io/sv2/1.png",
    "data:image/png;base64,AAAA",
    "not a url",
    "",
    null,
    undefined,
  ]) {
    assert.equal(isOptimizableImageSource(src), false, `${src} should not be optimizable`);
    assert.equal(optimizedImageUrl(src, 256), src);
    assert.equal(optimizedImageSrcSet(src, [128, 256]), undefined);
  }
});

test("widths snap up to a configured bucket so the optimizer never 400s", () => {
  assert.equal(snapImageWidth(40), 48);
  assert.equal(snapImageWidth(48), 48);
  assert.equal(snapImageWidth(185), 256);
  assert.equal(snapImageWidth(1), 16);
  // Above the largest bucket we clamp rather than emit an unconfigured width.
  assert.equal(snapImageWidth(99999), 3840);
  for (const bad of [0, -10, NaN, null, "wide"]) {
    assert.equal(snapImageWidth(bad), null);
  }
  assert.equal(optimizedImageUrl(CARD, 0), CARD);
});

test("srcSet is ascending, de-duplicated after snapping, and width-descriptor formatted", () => {
  // 40 and 48 both snap to 48: one candidate, not two transforms of the same
  // artwork at the same width.
  const srcSet = optimizedImageSrcSet(CARD, [256, 40, 48, 128]);
  assert.equal(
    srcSet,
    [
      `${optimizedImageUrl(CARD, 48)} 48w`,
      `${optimizedImageUrl(CARD, 128)} 128w`,
      `${optimizedImageUrl(CARD, 256)} 256w`,
    ].join(", "),
  );
});

test("the optimizable host list matches next.config.mjs remotePatterns", () => {
  // A host allowed here but missing from the config is a 400 at runtime, and a
  // host in the config but not here is a needlessly broad proxy allowance.
  const config = readFileSync(path.join(process.cwd(), "next.config.mjs"), "utf8");
  const configured = [...config.matchAll(/hostname:\s*"([^"]+)"/g)].map((m) => m[1]).sort();
  const source = readFileSync(path.join(process.cwd(), "lib/images/remoteImageDelivery.mjs"), "utf8");
  const allowed = [...source.matchAll(/"(images\.[^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(allowed, configured);
});
