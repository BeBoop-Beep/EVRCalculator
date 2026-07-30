// The mobile/tablet set picker: layering over the local tabs, and set-to-set
// navigation actually committing.
//
// TWO INDEPENDENT DEFECTS, BOTH BELOW 1200px
// ------------------------------------------
// 1. LAYERING. The open listbox declares `z-50`, but that z-index is sealed
//    inside a stacking context it cannot escape: the hero `<section>` carries
//    `backdrop-filter` (from `.set-context-premium`), and backdrop-filter
//    creates a stacking context. The tab strip's own container carries
//    `backdrop-blur-md`, creating a second one at the same level that paints
//    LATER in DOM order — so the tabs painted over the menu. Measured live at
//    320/390/430/834/1199px, `elementFromPoint` across the overlap band
//    returned a tab button, and the first option was not hit-testable.
//
//    The fix is not a bigger z-index on the listbox (which cannot leave the
//    trap) and not a portal (not needed): it raises the picker ROW — an
//    ancestor of the menu and an earlier sibling of the tabs — into a
//    positioned stacking context above them. It stays inside the sticky block's
//    own context, itself inside an `isolation: isolate` container, so the
//    global header is out of reach by construction.
//
// 2. SELECTION NEVER COMMITTED. The document-level dismiss handler closes the
//    picker whenever the event target is not inside `[data-set-picker]`, and
//    that marker existed ONLY on the two desktop picker wrappers. A
//    mousedown/touchstart on a mobile OPTION therefore counted as an outside
//    click: the listbox unmounted before the option's `click` could fire, so
//    `handleHeroSetSelect` never ran. Measured live: tapping "Paldea Evolved"
//    closed the menu and left the URL and the set identity unchanged.
//
//    The route construction was never at fault — `handleTargetIdChange` already
//    builds the canonical href, preserves the active tab and no-ops on the
//    active set. The fix is to let the mobile subtree opt into the existing
//    contract.
//
// RipStatisticsPageClient.jsx cannot be imported outside the Next build (it
// uses extensionless "@/..." specifiers only the bundler resolves), so these are
// source assertions, matching every other contract test for this page. The file
// carries mixed CRLF/LF, so it is normalised first.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

// The real routing helper and the real slug function, exercised for real.
//
// Neither can be imported directly here: the helper uses the bundler-only
// "@/utils/slugify" specifier, and `utils/slugify.js` is resolved as CommonJS
// outside the Next build so its named exports are not visible. Both project
// sources are therefore read verbatim and linked into one ES module — the slug
// rules and the href rules under test are the shipped ones, not a copy.
const slugifySource = read("../../utils/slugify.js")
  .replace(/export function/g, "function")
  .replace(/\btoSetSlug\b/g, "toCanonicalSetSlug");
const routingSource = read("../../lib/explore/ripStatisticsRouting.js").replace(
  /^import \{[^}]*\} from "@\/utils\/slugify";\n/m,
  ""
);
const { buildTargetHrefById, buildTcgSetHrefFromTarget, findTargetBySetSlug, resolveSetDetailTab } = await import(
  `data:text/javascript;base64,${Buffer.from(`${slugifySource}\n${routingSource}`, "utf8").toString("base64")}`
);

const source = read("RipStatisticsPageClient.jsx");
const hero = read("../pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.jsx");
const css = read("../../app/styles/globals.css");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

const count = (text, pattern) => (text.match(pattern) || []).length;

const stickyBlock = between(source, "data-set-detail-sticky-tabs", "<section\n                  data-set-context-header");
const dismissEffect = between(source, "if (!heroSetPickerOpen || typeof document === \"undefined\") {", "}, [heroSetPickerOpen]);");
const selection = between(source, "const handleHeroSetSelect = (target) => {", "const handleSetPickerKeyDown");
const targetChange = between(source, "const handleTargetIdChange = (nextTargetId, options = {}) => {", "const handleHeroSetSelect");

// ===========================================================================
// A. Layering — the open menu paints above the local tabs
// ===========================================================================

test("the mobile picker row is the element raised above the tabs", () => {
  // An ancestor of the menu and an earlier sibling of the tab strip.
  assert.ok(
    stickyBlock.includes('<div data-set-sticky-picker data-set-picker className="relative z-30 desk:hidden">'),
    "the picker row is a positioned stacking context above the tabs, below desktop only"
  );
  assert.ok(
    stickyBlock.indexOf("data-set-sticky-picker") < stickyBlock.indexOf("<SectionViewTabs"),
    "the closed picker row still reads as the top row of the unified sticky block"
  );
});

test("the raise is on the row because the listbox's own z-index cannot escape", () => {
  // Documented so a future edit does not "simplify" this back to a bigger
  // z-index on the listbox.
  const heroSection = between(hero, "<section", "<div data-hero-region");
  assert.ok(heroSection.includes("set-context-premium"), "the hero opts into the premium surface");
  assert.match(
    css,
    /\.set-context-premium \{[\s\S]*?backdrop-filter:/,
    "that surface applies backdrop-filter, which creates the stacking context trapping the menu"
  );
  const tabStrip = between(source, 'if (variant === "primary") {', "if (variant === \"secondary\")");
  assert.ok(tabStrip.includes("backdrop-blur-md"), "the tab strip creates its own, later-painting context");
  // The listbox keeps its z-index (it still has to sit above the hero's own
  // content), but nothing depends on it escaping the hero.
  assert.ok(hero.includes("z-50 max-h-56"), "the listbox z-index and height cap are unchanged");
});

test("no ancestor between the menu and the sticky block clips it", () => {
  assert.ok(
    source.includes('<div data-set-context-shell className="set-detail-context-shell overflow-visible'),
    "the shell stays overflow-visible"
  );
  const stickyTag = between(stickyBlock, "className=\"set-detail-sticky-tabs", "aria-busy");
  assert.ok(!/overflow-hidden|overflow-clip|overflow-x-clip/.test(stickyTag), "the sticky wrapper does not clip");
  const pickerRow = between(stickyBlock, "data-set-sticky-picker", "<SectionViewTabs");
  assert.ok(!/overflow-hidden|overflow-clip/.test(pickerRow), "nor does the picker row");
  // The hero's own surface must not clip the menu that overhangs it either.
  assert.ok(!/overflow-hidden|overflow-clip/.test(hero), "nor the hero section");
});

test("the menu overlays rather than displacing the tabs", () => {
  const menu = between(hero, "{isPickerExpanded ? (", "</div>\n        ) : null}");
  assert.ok(menu.includes("absolute right-0 top-[calc(100%+0.5rem)]"), "the menu is out of flow, so the tabs cannot move");
  assert.ok(menu.includes("max-h-56"), "and it is height-capped rather than pushing the page");
});

test("the menu stays inside a 320px viewport and scrolls internally", () => {
  const menu = between(hero, "{isPickerExpanded ? (", "</div>\n        ) : null}");
  assert.ok(menu.includes("overflow-y-auto"), "the option list scrolls inside its own box");
  assert.ok(menu.includes("max-h-56"), "so a long list cannot run off the bottom of the page");
  assert.ok(menu.includes("right-0"), "anchored to the trigger's edge, so it grows inward");
  assert.ok(!/\bleft-0\b/.test(menu), "it must not be pinned to both edges and forced wider than the gutter");
  // Long set names stay on one readable line rather than reflowing the row.
  assert.ok(menu.includes('<span className="min-w-0 flex-1 truncate">{target.name}</span>'));
  assert.ok(menu.includes("min-h-11"), "options keep a 44px touch target");
});

test("the picker row raise cannot outrank the global header", () => {
  // The row's z-index is resolved inside the sticky block's context, which sits
  // inside a container that isolates itself — so no value here can escape to
  // compete with the app header. Global navigation styling is untouched.
  assert.match(css, /\.set-detail-sticky-tabs \{[\s\S]*?z-index: 40;/);
  assert.ok(source.includes("relative isolate"), "the page container isolates its own stacking context");
  assert.ok(!/z-\[?(?:9\d{2,}|\d{4,})/.test(stickyBlock), "no escalating z-index arms race in the sticky block");
});

// ===========================================================================
// B. Selection commits
// ===========================================================================

test("the mobile picker subtree opts into the dismiss handler's inside-test", () => {
  assert.ok(
    dismissEffect.includes('event.target.closest?.("[data-set-picker]")'),
    "the existing contract is unchanged"
  );
  // The marker now covers the mobile trigger AND its listbox, so neither a
  // mousedown nor a touchstart on an option reads as an outside click.
  assert.ok(stickyBlock.includes("data-set-sticky-picker data-set-picker"), "the mobile subtree is marked");
  // Attribute usages only (the handler's selector string and the explanatory
  // comment both mention the name too): one marker per picker composition.
  assert.equal(
    count(source, /data-set-picker (?:data-|className=)/g),
    3,
    "one marker per picker composition: two desktop wrappers plus the mobile row"
  );
});

test("the dismiss handler still closes on genuine outside pointer input and Escape", () => {
  assert.ok(dismissEffect.includes('document.addEventListener("mousedown", handleOutsideClick)'));
  assert.ok(dismissEffect.includes('document.addEventListener("touchstart", handleOutsideClick, { passive: true })'));
  assert.ok(dismissEffect.includes('document.addEventListener("keydown", handleEscape)'));
  assert.ok(dismissEffect.includes('if (event.key === "Escape")'));
  // Every listener is removed, so an opened picker cannot leave the page in a
  // state that swallows later input.
  for (const removed of ["mousedown", "touchstart", "keydown"]) {
    assert.ok(dismissEffect.includes(`document.removeEventListener("${removed}"`), `${removed} is cleaned up`);
  }
  assert.ok(!/document.body.style|overflow = "hidden"/.test(dismissEffect), "opening the picker never locks the page");
});

test("Escape returns focus to the control that opened the menu", () => {
  assert.ok(
    dismissEffect.includes("document.activeElement.matches?.('[aria-haspopup=\"listbox\"]')"),
    "the opener is captured at open time, before arrow keys move focus into the list"
  );
  assert.ok(dismissEffect.includes("(opener || fallback)?.focus?.()"), "and focus is handed back on Escape");
  assert.ok(
    dismissEffect.includes('[aria-haspopup="listbox"][aria-expanded="true"]:not([aria-hidden="true"])'),
    "the fallback resolves the operable trigger, never the non-owner composition"
  );
});

test("selection routes through the one canonical navigation helper", () => {
  assert.ok(selection.includes('handleTargetIdChange(String(target?.target_id || ""));'));
  assert.ok(
    selection.indexOf("handleTargetIdChange") < selection.indexOf("setHeroSetPickerOpen(false)"),
    "navigation is accepted before the menu closes"
  );
  // No second routing system: one href map, one push.
  assert.ok(targetChange.includes("targetHrefById?.[nextTargetId]"), "the canonical href map builds the destination");
  assert.equal(count(targetChange, /router\.push\(/g), 2, "one push per branch, no window.location fallback");
  assert.ok(!/window\.location/.test(targetChange), "no full-page reload");
  assert.ok(!/href\s*=\s*`\/TCGs/.test(targetChange), "no hardcoded route is assembled here");
});

test("the active tab is carried to the destination set", () => {
  assert.ok(
    targetChange.includes("appendSetDetailIntentToHref(targetHrefById?.[nextTargetId] || null, { tab: setDetailTab })"),
    "the current local tab is appended to the canonical href"
  );
  // And set-specific context that would be invalid on another set is not.
  const appendHelper = between(source, "function appendSetDetailIntentToHref(", "const SIMPLE_PILLAR_INFO_COPY");
  assert.ok(appendHelper.includes('params.set("tab", nextTab)'));
  assert.ok(appendHelper.includes('params.delete("section")'), "a stale section anchor is dropped when none is requested");
});

test("selecting the already-active set closes the menu without navigating", () => {
  assert.ok(
    targetChange.includes('if (String(nextTargetId) === String(requestedTargetId || "")) {\n      return;\n    }'),
    "the helper no-ops on the active set, so no navigation loop can start"
  );
  // handleHeroSetSelect still closes, because the close is unconditional.
  assert.ok(selection.includes("setHeroSetPickerOpen(false);"));
});

test("navigation closes the picker once the new set actually lands", () => {
  assert.ok(
    source.includes("useEffect(() => {\n    setHeroSetPickerOpen(false);\n  }, [requestedTargetId]);"),
    "the route change itself closes the menu, so repeated switching cannot leave one open"
  );
});

test("a stale old-set response cannot overwrite the new set", () => {
  const guard = between(source, "function isSetStateForActiveSet(", "function getSetValueScopeLabel(");
  assert.ok(guard.includes("const stateToken = normalizeSetIdentityToken(stateSetId);"));
  assert.ok(guard.includes("return activeTokens.includes(stateToken);"), "state is accepted only if it names the ACTIVE set");
  assert.ok(guard.includes("selectedTargetMatchesRequest"), "a selectedTarget lagging the route does not widen the match");
  // And the guard is actually applied to the in-flight fetch states.
  assert.ok(count(source, /isSetStateForActiveSet\(/g) >= 3, "the guard gates the set-scoped fetch states");
});

test("there is exactly one picker owner and one listbox below desktop", () => {
  assert.equal(count(source, /<PokemonSetMobileHero/g), 1, "the mobile hero is mounted once");
  assert.ok(source.includes("isPickerOwner={!isDesktopHeroComposition}"), "one width reading decides ownership");
  assert.equal(count(source, /const \[heroSetPickerOpen, setHeroSetPickerOpen\] = useState/g), 1);
  // A non-owner renders no listbox at all and is out of the tab order.
  assert.ok(hero.includes("const isPickerExpanded = isPickerOwner && Boolean(pickerOpen);"));
  assert.ok(hero.includes("tabIndex={isPickerOwner ? 0 : -1}"));
  assert.ok(hero.includes("aria-hidden={isPickerOwner ? undefined : true}"));
  assert.equal(count(hero, /role="listbox"/g), 1);
});

test("aria wiring, keyboard navigation and active-option state are preserved", () => {
  assert.ok(hero.includes("aria-expanded={isPickerExpanded}"));
  assert.ok(hero.includes('aria-haspopup="listbox"'));
  assert.ok(hero.includes("aria-controls={listboxId}"));
  assert.ok(source.includes('listboxId="set-mobile-picker-list"'));
  assert.ok(hero.includes("onKeyDown={onPickerKeyDown}"), "the listbox owns arrow-key movement");
  assert.ok(hero.includes('aria-selected={isSelected}'));
  assert.ok(hero.includes('String(target.target_id) === String(selectedTargetId || "")'), "active option from the route");
  const keyNav = between(source, "const handleSetPickerKeyDown = (event) => {", "const handleTargetChange");
  for (const key of ["ArrowDown", "ArrowUp", "Home", "End"]) {
    assert.ok(keyNav.includes(`"${key}"`), `${key} is handled`);
  }
  assert.ok(keyNav.includes("options[nextIndex]?.focus();"));
});

// ===========================================================================
// C. Desktop untouched
// ===========================================================================

test("the 1200px+ picker composition is unchanged", () => {
  assert.ok(
    source.includes('<div ref={heroSetPickerRef} data-set-picker data-compact-set-picker className="relative z-20 col-span-2'),
    "the desktop context-header picker keeps its own wrapper and z-index"
  );
  assert.ok(
    source.includes('<div ref={heroSetPickerRef} data-set-picker data-hero-picker className="relative w-full">'),
    "and so does the hero picker"
  );
  assert.ok(source.includes("aria-expanded={isDesktopHeroComposition && heroSetPickerOpen}"));
  assert.ok(stickyBlock.includes("desk:hidden"), "the raised mobile row does not exist at 1200px+");
});

test("global navigation styling is not touched by the fix", () => {
  assert.ok(!/data-app-header|site-header|GlobalNav/.test(stickyBlock));
  assert.ok(!/--app-header-offset:\s/.test(stickyBlock), "the header offset is read, never redefined here");
});

// ===========================================================================
// D. The route the picker navigates to — exercised for real
// ===========================================================================

const TARGETS = [
  { target_type: "set", target_id: "uuid-151", name: "Scarlet and Violet 151" },
  { target_type: "set", target_id: "uuid-obsidian", name: "Obsidian Flames" },
  { target_type: "set", target_id: "uuid-paradox", name: "Paradox Rift" },
];

test("the canonical href map produces the hyphenated set-detail route", () => {
  const hrefById = buildTargetHrefById(TARGETS);
  assert.equal(hrefById["uuid-151"], "/TCGs/Pokemon/Sets/scarlet-and-violet-151");
  assert.equal(hrefById["uuid-obsidian"], "/TCGs/Pokemon/Sets/obsidian-flames");
  assert.equal(hrefById["uuid-paradox"], "/TCGs/Pokemon/Sets/paradox-rift");
});

test("each tab survives the hop to another set", () => {
  for (const tab of ["overview", "cards", "pull-rates", "insights"]) {
    assert.equal(
      buildTcgSetHrefFromTarget(TARGETS[1], { tab }),
      `/TCGs/Pokemon/Sets/obsidian-flames?tab=${tab}`,
      `${tab} is carried to the destination set`
    );
    // And the destination route resolves that tab back to the same value.
    assert.equal(resolveSetDetailTab(tab), tab);
  }
});

test("the destination route resolves the slug back to the selected target", () => {
  // The route lowercases its param before matching, so the slug the picker
  // navigates to must round-trip.
  for (const target of TARGETS) {
    const href = buildTcgSetHrefFromTarget(target);
    const slug = href.split("/").pop();
    assert.equal(findTargetBySetSlug(TARGETS, slug)?.target_id, target.target_id);
    assert.equal(findTargetBySetSlug(TARGETS, slug.toUpperCase())?.target_id, target.target_id, "matching is case-insensitive");
  }
});
