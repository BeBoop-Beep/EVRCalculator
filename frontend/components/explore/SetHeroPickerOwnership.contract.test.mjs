import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

// Correction 2. Two lightweight hero compositions are mounted with one hidden
// by CSS. display:none does not unmount, so ownership of the set picker has to
// be explicit rather than visual, or the page ends up with two operable
// triggers, two listboxes and two focus stops.

test("one width reading decides which composition owns the picker", () => {
  assert.ok(
    source.includes('const isDesktopHeroComposition = useMediaQuery("(min-width: 1200px)", true);'),
    "a single reading drives both compositions, seeded desktop for SSR"
  );
  assert.ok(
    source.includes("isPickerOwner={!isDesktopHeroComposition}"),
    "the mobile hero owns the picker only below 1200px"
  );
});

test("the desktop trigger yields ownership below 1200px", () => {
  assert.ok(source.includes("aria-expanded={isDesktopHeroComposition && heroSetPickerOpen}"));
  assert.ok(source.includes("aria-hidden={isDesktopHeroComposition ? undefined : true}"));
  assert.ok(source.includes("tabIndex={isDesktopHeroComposition ? 0 : -1}"));
});

test("only the owning composition mounts a listbox", () => {
  assert.ok(
    source.includes("{isDesktopHeroComposition && heroSetPickerOpen ? (") &&
      source.includes('id="compact-set-picker-list"'),
    "the desktop listbox is gated on desktop ownership"
  );
});

test("the two listbox ids can never collide", () => {
  assert.equal((source.match(/id="compact-set-picker-list"/g) || []).length, 1);
  assert.equal((source.match(/listboxId="set-mobile-picker-list"/g) || []).length, 1);
  assert.ok(!source.includes('listboxId="compact-set-picker-list"'), "the mobile hero must not reuse the desktop id");
});

test("open state is shared and is closed when the boundary is crossed", () => {
  // One owner, one state. Resizing across 1200px must not hand a half-open menu
  // to the other composition.
  assert.equal(
    (source.match(/const \[heroSetPickerOpen, setHeroSetPickerOpen\] = useState/g) || []).length,
    1,
    "there is exactly one picker open-state owner"
  );
  assert.ok(
    /useEffect\(\(\) => \{\s*setHeroSetPickerOpen\(false\);\s*\}, \[isDesktopHeroComposition\]\);/.test(source),
    "crossing the boundary closes the picker"
  );
});

test("the two compositions are mutually exclusive by class", () => {
  assert.ok(source.includes('<div className="desk:hidden max-desk:mt-2">'), "the mobile hero is hidden at desktop");
  assert.ok(
    source.includes("relative min-h-[88px] overflow-visible rounded-t-xl border max-desk:hidden desk:order-1 md:rounded-t-2xl"),
    "the desktop hero is hidden below desktop and keeps its desktop reading order"
  );
});

test("the hero model is identity only", () => {
  // Set Value and RIP were duplicated readings; the mobile header no longer
  // consumes them, which also removes the memo's dependency on
  // setHeaderSummary (and with it the temporal-dead-zone crash that read it
  // before declaration).
  const heroModel = source.slice(
    source.indexOf("const mobileHeroModel = useMemo("),
    source.indexOf("// Correction 2: two lightweight hero compositions")
  );
  assert.ok(heroModel.length > 0, "the hero model must be locatable");
  for (const identity of ["setName: selectedName", "era: selectedTarget?.era", "logoUrl: heroLogoUrl"]) {
    assert.ok(heroModel.includes(identity), `${identity} must remain`);
  }
  for (const gone of ["setHeaderSummary", "topScoreRaw", "setContextRipTier", "recommendationBadge", "setValue:", "rip:"]) {
    assert.ok(!heroModel.includes(gone), `${gone} must not reach the identity-only header`);
  }
});

test("the hero model is declared after every value it reads", () => {
  // A useMemo dependency array is evaluated eagerly during render, so a
  // dependency on a const declared further down throws
  // "Cannot access 'X' before initialization" at runtime while the build still
  // compiles — which is exactly why this needs a test.
  const heroModel = source.indexOf("const mobileHeroModel = useMemo(");
  assert.ok(heroModel >= 0, "the hero model must be locatable");
  for (const dependency of ["const selectedName =", "const heroLogoUrl ="]) {
    const declared = source.indexOf(dependency);
    assert.ok(declared >= 0, `${dependency} must be locatable`);
    assert.ok(declared < heroModel, `${dependency.trim()} must be initialized before the hero model reads it`);
  }
});

test("the mobile hero adds no request, no fetch and no duplicate computation", () => {
  const heroModel = source.slice(
    source.indexOf("const mobileHeroModel = useMemo("),
    source.indexOf("// Correction 2: two lightweight hero compositions")
  );
  for (const forbidden of ["fetch(", "useEffect", "useSectionFetchState", "await "]) {
    assert.ok(!heroModel.includes(forbidden), `the hero model must not ${forbidden}`);
  }
});

