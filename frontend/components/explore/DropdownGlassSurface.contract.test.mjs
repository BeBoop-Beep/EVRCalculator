// Shared dropdown glass: the header "My Portfolio" menu, the three set-picker
// listboxes (hero, compact, mobile) and the Sealed Market product trigger all
// have to read as the same translucent material as the set-page context cards.
//
// Before this pass each surface hardcoded its own opaque `bg-[var(--surface-panel)]`
// plus a one-off shadow, so the set picker painted as a solid navy block over
// the set artwork while the header menu used a different opacity again. The fix
// is one class (`.set-dropdown-glass`) built from the existing --set-glass-*
// tokens, not three near-identical RGBA values.
//
// These are source assertions: RipStatisticsPageClient.jsx and Header.js use
// extensionless "@/..." specifiers that only the Next bundler resolves, so they
// cannot be imported here — matching every other contract test for this page.
// RipStatisticsPageClient.jsx carries mixed CRLF/LF, so sources are normalised.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const header = read("../Header.js");
const page = read("RipStatisticsPageClient.jsx");
const mobileHero = read("../pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.jsx");
const sealedCard = read("../pokemon/set-page/Overview/SealedMarketTrendCard.jsx");

test("the shared dropdown glass class exists and is built from the set-page glass tokens", () => {
  assert.match(css, /\.set-dropdown-glass,\n\s*\.set-dropdown-glass-trigger \{/);

  const surface = css.slice(css.indexOf(".set-dropdown-glass,"));
  // Border and top highlight come from the shared tokens, not new literals.
  assert.match(surface, /border: 1px solid var\(--set-dropdown-glass-border, var\(--set-glass-border\)\)/);
  assert.match(surface, /inset 0 1px 0 var\(--set-dropdown-glass-highlight, var\(--set-glass-highlight\)\)/);
  assert.match(surface, /var\(--set-dropdown-glass-shadow\)/);

  // The translucent layer and blur live behind a @supports guard so browsers
  // without backdrop-filter keep an opaque, readable fallback background.
  assert.match(
    css,
    /@supports \(\(backdrop-filter: blur\(18px\)\) or \(-webkit-backdrop-filter: blur\(18px\)\)\)/
  );
  const fallback = surface.slice(0, surface.indexOf("@supports"));
  assert.match(fallback, /background: var\(--set-dropdown-glass-fallback\)/);
  assert.match(css, /--set-dropdown-glass-fallback: linear-gradient\(135deg, rgba\(6, 14, 26, 0\.99\), rgba\(7, 16, 29, 0\.98\)\);/);

  const supported = css.slice(css.indexOf("@supports ((backdrop-filter"));
  assert.match(supported, /background: var\(--set-dropdown-glass-bg\)/);
  assert.match(supported, /backdrop-filter: blur\(var\(--set-dropdown-glass-blur, 18px\)\) saturate\(130%\)/);
  assert.match(supported, /-webkit-backdrop-filter: blur\(var\(--set-dropdown-glass-blur, 18px\)\) saturate\(130%\)/);
});

test("the dropdown material is frosted privacy glass: opaque enough to hide detail, still translucent", () => {
  assert.match(
    css,
    /--set-dropdown-glass-bg:\n\s*radial-gradient\(circle at 18% 0%, rgba\(96, 165, 250, 0\.07\), transparent 34%\),\n\s*linear-gradient\(135deg, rgba\(6, 14, 26, 0\.94\), rgba\(7, 16, 29, 0\.90\)\);/
  );

  const alphas = /--set-dropdown-glass-bg:[\s\S]*?;/
    .exec(css)[0]
    .match(/rgba\([^)]*\)/g)
    .map((value) => Number(value.split(",").pop().replace(")", "").trim()));

  // Never fully opaque — colour and atmosphere behind the menu must still
  // come through, or this stops being glass and becomes a flat block.
  for (const alpha of alphas) {
    assert.ok(alpha > 0 && alpha < 1, `expected a translucent alpha, got ${alpha}`);
  }

  // Frosted floor. Two earlier passes (0.78/0.68, then 0.88/0.82) both left the
  // page behind legible; the base stops now sit at/above 0.90.
  const base = alphas.filter((alpha) => alpha > 0.5);
  assert.equal(base.length, 2);
  assert.ok(Math.min(...base) >= 0.90, `frosted base must stay >= 0.90, saw ${Math.min(...base)}`);
  assert.ok(Math.max(...base) <= 0.96, "a base above ~0.96 stops reading as glass");

  // Blur is the other half of frosting: opacity limits how much light passes,
  // blur destroys the detail in whatever does. It must clearly exceed the
  // context-card blur so a menu over a glass card stays distinct.
  assert.match(css, /--set-dropdown-glass-blur: 18px;/);
  const dense = Number(/--set-glass-blur-dense: (\d+)px;/.exec(css)[1]);
  assert.ok(18 >= dense * 3, `dropdown blur must dominate the ${dense}px context-card blur`);
});

test("dropdown tokens no longer alias the lighter context-card glass", () => {
  // A menu sitting on top of a glass card has to be denser than that card,
  // so border and highlight carry their own values now.
  assert.match(css, /--set-dropdown-glass-border: rgba\(148, 180, 220, 0\.15\);/);
  assert.match(css, /--set-dropdown-glass-highlight: rgba\(255, 255, 255, 0\.045\);/);
  assert.match(css, /--set-dropdown-glass-shadow: 0 18px 42px rgba\(1, 5, 15, 0\.42\);/);

  // Context-card glass itself is untouched by the frosting pass.
  assert.match(css, /--set-glass-bg: rgba\(8, 17, 31, 0\.40\);/);
  assert.match(css, /--set-glass-bg-dense: rgba\(8, 17, 31, 0\.52\);/);
  assert.match(css, /--set-glass-border: rgba\(145, 174, 212, 0\.14\);/);
  assert.match(css, /--set-glass-blur: 4px;/);
});

test("light theme re-tints the same glass so dark option text stays readable", () => {
  // The header menu previously used --surface-panel (white in light theme).
  // Moving it onto the shared dark glass would have painted near-black text on
  // navy, so every dropdown token is overridden for [data-theme="light"].
  const light = css.slice(css.indexOf('[data-theme="light"] {'));
  const block = light.slice(0, light.indexOf("\n}"));

  for (const token of [
    "--set-dropdown-glass-bg",
    "--set-dropdown-glass-fallback",
    "--set-dropdown-glass-border",
    "--set-dropdown-glass-highlight",
    "--set-dropdown-glass-shadow",
    "--set-dropdown-glass-hover",
    "--set-dropdown-glass-active",
  ]) {
    assert.ok(block.includes(`${token}:`), `light theme must override ${token}`);
  }

  // Light surface stays light and still translucent — same frosted material,
  // not a muddy dark menu and not a second hardcoded design.
  assert.match(block, /--set-dropdown-glass-bg:[\s\S]*?rgba\(255, 255, 255, 0\.97\), rgba\(244, 248, 253, 0\.94\)/);
  assert.match(block, /--set-dropdown-glass-blur: 18px;/);
  assert.doesNotMatch(block, /--set-dropdown-glass-bg:[\s\S]*?rgba\(8, 17, 31/);
  assert.match(block, /--set-dropdown-glass-hover: rgba\(15, 23, 42, 0\.06\);/);
  assert.match(block, /--set-dropdown-glass-active: rgba\(15, 23, 42, 0\.09\);/);
  // The dark hover wash would be invisible on a light panel and vice versa.
  assert.doesNotMatch(block, /--set-dropdown-glass-hover: rgba\(148, 180, 220/);
});

test("option rows use a restrained shared wash rather than a filled block or a bordered button", () => {
  assert.match(css, /\.set-dropdown-option:hover,\n\s*\.set-dropdown-option:focus-visible \{\n\s*background: var\(--set-dropdown-glass-hover\);/);
  assert.match(css, /--set-dropdown-glass-hover: rgba\(148, 180, 220, 0\.10\);/);
  assert.match(css, /--set-dropdown-glass-active: rgba\(148, 180, 220, 0\.14\);/);

  // The selected row is an accent wash, not a solid surface-page block.
  assert.match(css, /\.set-dropdown-option\[aria-selected="true"\][\s\S]*?background: var\(--set-dropdown-glass-active\);/);

  const optionRules = css.slice(css.indexOf(".set-dropdown-option:hover"), css.indexOf(".set-dropdown-glass-trigger:hover"));
  assert.doesNotMatch(optionRules, /\bborder:/, "option rows must not gain their own border");
});

test("the My Portfolio menu uses the shared glass and keeps its width, items and active accent", () => {
  assert.match(header, /const navDropdownSurface = "set-dropdown-glass";/);
  assert.ok(header.includes("const navDropPanel = `absolute top-full mt-1 rounded-xl ${navDropdownSurface}"));

  // The panel must not re-declare a competing opaque background or border.
  const panel = /const navDropPanel = `[^`]*`;/.exec(header)[0];
  assert.doesNotMatch(panel, /bg-\[var\(--surface-panel\)\]/);
  assert.doesNotMatch(panel, /border border-/);

  // Dimensions, spacing and typography are untouched.
  assert.match(header, /const navDropPanelCompact = "w-36";/);
  assert.match(header, /const navDropPanelAccount = "w-48";/);
  assert.match(header, /const navDropItem = "set-dropdown-option block w-full px-4 py-2 text-\[15px\] leading-5 text-left/);
  assert.doesNotMatch(/const navDropItem = "[^"]*";/.exec(header)[0], /hover:bg-\[var\(--surface-hover\)\]/);

  // Trigger, caret and the active yellow underline are unchanged.
  assert.match(header, /after:bg-\[var\(--accent\)\]/);
  assert.match(header, /isCollectionDropdownOpen \? 'rotate-180' : ''/);

  // Navigation destinations are unchanged.
  for (const href of ["/my-portfolio", "/my-portfolio/collection", "/my-portfolio/wishlist"]) {
    assert.ok(header.includes(`href="${href}"`), `expected ${href} to remain a menu destination`);
  }
});

test("all three set-picker listboxes use the shared glass and keep their dimensions and scrollbar", () => {
  const listboxes = [
    // Compact (desktop context header) picker.
    /className="index-scrollbar set-dropdown-glass absolute left-0 top-\[calc\(100%\+0\.5rem\)\] z-50 max-h-56 w-full min-w-\[16rem\] overflow-y-auto rounded-xl p-1\.5"/,
    // Hero picker.
    /className="index-scrollbar set-dropdown-glass absolute left-1\/2 top-full z-30 mt-2 max-h-72 w-\[min\(36rem,92vw\)\] -translate-x-1\/2 overflow-y-auto rounded-xl p-1\.5 text-left"/,
  ];
  for (const pattern of listboxes) assert.match(page, pattern);

  // Mobile overlay picker.
  assert.match(
    mobileHero,
    /className="index-scrollbar set-dropdown-glass absolute right-0 top-\[calc\(100%\+0\.5rem\)\] z-50 max-h-56 w-full min-w-\[16rem\] overflow-y-auto rounded-xl p-1\.5"/
  );

  // No picker keeps the old opaque panel, its one-off shadow or its own border.
  for (const source of [page, mobileHero]) {
    assert.doesNotMatch(source, /role="listbox"[\s\S]{0,400}?bg-\[var\(--surface-panel\)\]/);
    assert.doesNotMatch(source, /shadow-\[0_14px_34px_rgba\(0,0,0,0\.45\)\]/);
  }
  assert.doesNotMatch(page, /shadow-\[0_12px_30px_rgba\(0,0,0,0\.42\)\]/);

  // The teal index scrollbar is preserved on every picker.
  assert.equal((page.match(/index-scrollbar set-dropdown-glass/g) || []).length, 2);
  assert.match(css, /\.index-scrollbar::-webkit-scrollbar-thumb \{\n\s*background: rgba\(45, 212, 191, 0\.45\);/);
});

test("set-picker rows use the shared wash and the current set keeps a subtle accent, not a solid block", () => {
  // Scoped to the picker option rows only: unrelated pills elsewhere on the
  // page legitimately still use the surface-page hover.
  const optionRows = [page, mobileHero].flatMap((source) =>
    [...source.matchAll(/role="option"[\s\S]{0,600}?className=\{`([\s\S]*?)`\}/g)].map((match) => match[1])
  );
  assert.equal(optionRows.length, 3, "expected the hero, compact and mobile option rows");

  for (const row of optionRows) {
    assert.match(row, /^set-dropdown-option flex/);
    // The old solid selected block and the 70%-opacity page hover are gone.
    assert.doesNotMatch(row, /bg-\[var\(--surface-page\)\]/);
    assert.doesNotMatch(row, /hover:bg-/);
  }

  // "Current" stays an accent word, not a filled badge.
  for (const source of [page, mobileHero]) {
    assert.match(source, /text-xs font-medium text-\[var\(--accent\)\]">Current</);
  }
});

test("set-picker navigation, ownership and list content are unchanged by the styling pass", () => {
  // Selection still commits through the existing handler, and the dismiss
  // contract marker is still present on every picker subtree.
  assert.match(page, /onClick=\{\(\) => handleHeroSetSelect\(target\)\}/);
  assert.match(page, /\[data-set-picker\]/);
  assert.match(mobileHero, /onClick=\{\(\) => onSelectTarget\(target\)\}/);

  // The list is still rendered from switcherTargets in its incoming order —
  // this pass does not sort or filter sets.
  assert.match(page, /switcherTargets\.map\(\(target\) => \{/);
  assert.doesNotMatch(page, /switcherTargets\s*\n?\s*\.sort\(/);
});

test("the Sealed Market trigger uses the shared glass and keeps its size, label and native behavior", () => {
  assert.match(
    sealedCard,
    /className="set-dropdown-glass-trigger h-10 w-full min-w-0 appearance-none truncate rounded-lg pl-2 pr-10 text-xs text-\[var\(--text-primary\)\]"/
  );
  assert.doesNotMatch(sealedCard, /bg-\[var\(--surface-panel\)\]/);

  // Still a native <select>: no custom listbox was introduced for this pass.
  assert.match(sealedCard, /<select/);
  assert.doesNotMatch(sealedCard, /role="listbox"/);

  // Accessible label, title and the existing selection handler are preserved,
  // and switching products still triggers no extra fetch.
  assert.match(sealedCard, /<span className="sr-only">Sealed product<\/span>/);
  assert.match(sealedCard, /onChange=\{\(event\) => setSelectedId\(event\.target\.value\)\}/);
  assert.doesNotMatch(/onChange=\{[^}]*\}/.exec(sealedCard)[0], /fetch|retry/);

  // OS-drawn option panels only get a readable, theme-aware fallback.
  assert.match(css, /\.set-dropdown-glass-trigger option \{\n\s*background-color: var\(--surface-panel\);\n\s*color: var\(--text-primary\);/);
  assert.match(css, /\.set-dropdown-glass-trigger:hover \{\n\s*border-color: rgba\(148, 180, 220, 0\.24\);/);
});

test("the Sealed Market trigger is neutral on pointer focus and yellow only for keyboard", () => {
  // The global form rule paints accent + yellow glow on ANY focus. It is still
  // there for real inputs; the dropdown trigger opts out of it.
  assert.match(css, /input:focus,\ntextarea:focus,\nselect:focus \{\n\s*border-color: var\(--accent\);\n\s*box-shadow: 0 0 0 3px rgba\(250, 204, 21, 0\.2\);/);

  const plainFocus = /select\.set-dropdown-glass-trigger:focus,\n\.set-dropdown-glass-trigger:focus \{[\s\S]*?\n\}/.exec(css)[0];
  const keyboardFocus = /select\.set-dropdown-glass-trigger:focus-visible,\n\.set-dropdown-glass-trigger:focus-visible \{[\s\S]*?\n\}/.exec(css)[0];

  // Rest/hover/pointer-focus are the same material: no accent, no gray halo,
  // no browser outline.
  assert.match(plainFocus, /outline: none;/);
  assert.match(plainFocus, /border-color: var\(--set-dropdown-glass-border/);
  assert.doesNotMatch(plainFocus, /--accent|rgba\(250, 204, 21/);
  assert.doesNotMatch(plainFocus, /0 0 0 3px/);
  assert.match(plainFocus, /var\(--set-dropdown-glass-shadow\)/);

  // Keyboard focus keeps an accessible 2px accent ring.
  assert.match(keyboardFocus, /0 0 0 2px var\(--accent\)/);
  assert.match(keyboardFocus, /var\(--set-dropdown-glass-shadow\)/);

  // The element-qualified selector is what outranks `select:focus`; a bare
  // class would silently lose to it.
  assert.ok(css.includes("select.set-dropdown-glass-trigger:focus"));
  assert.ok(css.includes("select.set-dropdown-glass-trigger:focus-visible"));
  assert.doesNotMatch(plainFocus + keyboardFocus, /!important/);

  // Hover is a slightly brighter glass border, not a highlight.
  assert.match(css, /\.set-dropdown-glass-trigger:hover \{\n\s*border-color: rgba\(148, 180, 220, 0\.24\);/);

  // Focus handling lives in CSS, so no competing Tailwind ring utility remains
  // on the select (it would lose to the global rule anyway).
  const trigger = /className="set-dropdown-glass-trigger[^"]*"/.exec(sealedCard)[0];
  assert.doesNotMatch(trigger, /focus-visible:ring|focus:ring|ring-\[var\(--accent\)\]/);
  assert.doesNotMatch(trigger, /border-\[var\(--border-subtle\)\]/);
});

test("the Sealed Market caret reuses the set picker chevron and never blocks the label", () => {
  const CHEVRON = "M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z";

  // Byte-identical to the path the hero and compact set pickers draw.
  assert.ok(page.includes(CHEVRON), "set picker chevron must still exist");
  assert.ok(sealedCard.includes(CHEVRON), "Sealed Market must reuse that exact path");

  // Decorative, non-interactive, right-aligned, secondary colour.
  const caret = sealedCard.slice(sealedCard.indexOf('<span aria-hidden="true" className="pointer-events-none'), sealedCard.indexOf(CHEVRON));
  assert.match(caret, /pointer-events-none absolute right-3 top-1\/2 -translate-y-1\/2 text-\[var\(--text-secondary\)\]/);
  assert.match(caret, /viewBox="0 0 20 20"/);
  assert.match(caret, /className="h-4 w-4"/);

  // The OS arrow is suppressed and the label is padded clear of the caret.
  assert.match(sealedCard, /appearance-none/);
  assert.match(sealedCard, /pr-10/);
  assert.match(sealedCard, /<label className="relative mt-3 block min-w-0">/);
  // No second caret icon was introduced.
  assert.equal((sealedCard.match(/<svg/g) || []).length, 1);
});

test("making Sealed Market consistent did not touch the set picker or product behavior", () => {
  // The set picker is the reference: its trigger keeps its own focus classes.
  assert.match(page, /focus:outline-none focus-visible:ring-2 focus-visible:ring-\[var\(--accent\)\]/);
  assert.doesNotMatch(page, /set-dropdown-glass-trigger/);

  // Product ordering, default selection and the no-extra-request contract are
  // untouched by this styling pass.
  assert.match(sealedCard, /sortSealedProductsByCurrentPrice\(state\.payload\?\.products\)/);
  assert.match(sealedCard, /selectSealedProduct\(state\.payload, selectedId\)/);
  assert.match(sealedCard, /onChange=\{\(event\) => setSelectedId\(event\.target\.value\)\}/);
  assert.match(sealedCard, /orderedProducts\.map\(/);
  assert.match(sealedCard, /<span className="sr-only">Sealed product<\/span>/);
});

test("the shared surfaces agree on blur, border, highlight and corner-radius family", () => {
  // One class supplies border/background/shadow to all four surfaces, so
  // consistency is structural rather than four copies of the same literals.
  const consumers = [header, page, mobileHero, sealedCard];
  const usages = consumers.reduce(
    (total, source) => total + (source.match(/set-dropdown-glass(?!-)|set-dropdown-glass-trigger/g) || []).length,
    0
  );
  assert.ok(usages >= 5, `expected every dropdown surface to opt in, saw ${usages}`);

  // Corner-radius family: rounded-xl panels, rounded-lg rows and trigger.
  assert.match(header, /rounded-xl \$\{navDropdownSurface\}/);
  assert.match(page, /set-dropdown-glass[^"]*rounded-xl/);
  assert.match(sealedCard, /set-dropdown-glass-trigger[^"]*rounded-lg/);

  // Menus keep distinct widths — this is a shared material, not one component.
  assert.match(header, /w-36/);
  assert.match(page, /w-\[min\(36rem,92vw\)\]/);
});
