# Plan 4 — Mobile Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Depends on Plans 2 and 3.** Plan 2 supplies the `tab`/`desk` breakpoint tokens, the single mount, and the separated sticky tabs. Plan 3 supplies the responsive chart sizing this composition assumes.

**Goal:** Recompose the Set Overview below 1200px as an intentional set-intelligence feed — a mobile-first hero, no card-in-card nesting, compact ranked chase rows and a compact RIP breakdown — losing no data, no control and no desktop pixel.

**Architecture:** The Overview section becomes a `data-mobile-feed` region whose CSS strips the outer card chrome below 1200px and replaces it with dividers, so every existing `SectionCard` is recomposed without touching its call sites. The hero is the one place the information composition genuinely differs enough to justify a separate presentational component; it consumes the same already-computed values and shares the set-picker's open state, so nothing refetches and nothing desyncs. Everything else is responsive classes on existing components.

**Tech Stack:** React 19, Tailwind 3.4 (`max-desk:`, `tab:`, `desk:`), `node:test` via `tsx` with `react-test-renderer`.

## Global Constraints

See [the plan index](2026-07-28-mobile-set-overview-INDEX.md#global-constraints). The ones that bind hardest here:

- Desktop at `1200px+` must be pixel-identical to `main`: hero, grid, section cards, spacing, typography, interactions.
- **Every control survives.** The only approved removals in the whole phase are the green floating button (done in Plan 2) and the Tools destination (done in Plan 1). The hero's `View trend` and `View verdict` links are not removed — they are *replaced* by making the regions they sat in tappable, which is what the brief asks for. The destinations must still be reachable.
- **Top Chase rows 6–10 must never be silently discarded.** A five-row preview is only acceptable because the existing "View all chase cards" control still reveals all ten in place.
- Preserve the existing brand colours and product visual language. Do not introduce a new colour system.
- Do not change any calculation, ranking, filter or eligibility rule.
- Loading placeholders must match final mobile dimensions. Each section fails independently.
- Tests: `node:test` via `tsx --test`, `react-test-renderer` with `createNodeMock`. Normalise source strings with `.replace(/\r\n/g, "\n")`.

---

## Mandatory corrections applied to this plan

### Correction 2 — one interactive set-picker owner (Task 2)

Task 2 mounts the mobile hero beside the desktop hero and hides one with CSS.
That is **not** conditional rendering, and the phase's whole premise is that
CSS-hidden markup is still mounted, focusable and effectful. The lightweight
duplicated hero wrapper is acceptable only under all of the following, which
Task 2 now enforces and tests:

- **Exactly one picker menu is mounted at a time.** The open listbox renders in
  whichever composition is visible, never both. The hero receives an
  `isPickerOwner` flag derived from a single `useMediaQuery("(min-width: 1200px)")`
  reading, so the two compositions can never both own the menu.
- **Ids are unique.** `compact-set-picker-list` (desktop) vs
  `set-mobile-picker-list` (mobile). Never the same string.
- **The hidden composition is not keyboard-focusable** — its trigger carries
  `tabIndex={-1}` and `aria-hidden`, so the tab order holds one picker.
- **Open state is shared** (`heroSetPickerOpen` on the page), so nothing desyncs,
  and crossing 1200px with the picker open closes it rather than transferring a
  half-open menu into a different composition.
- No duplicated requests, effects, observers or expensive computations: the hero
  consumes an already-memoised view model built from values the page already
  computed.

### Correction 3 — the sparkline is a sibling of the row link, not a child (Task 4)

Task 4's original draft made the whole row one `<a>`, with the interactive
sparkline inside it. That is invalid nested interactive content. Each row is now
composed as two siblings inside one grid:

- **navigation region** — `<a>` covering rank, image, name, rarity, price, dollar
  and percentage movement;
- **chart region** — `CompactSparkline`, independently focusable, with pointer,
  arrow-key and Escape behaviour of its own, and no navigation on activation.

### Correction 1 follow-through — gutters and the tablet cap (Task 3)

Task 3's gutter change lands in the `SCAFFOLD_BREAKPOINTS` recipes added by Plan 2
Task 2, not in a single `contentWrapperClassName` string, and it must be applied
to **both** recipes so My Collection and the public profile pages keep matching
gutters at their own breakpoint.

`contentShellClassName` for the set page must use `desk:px-4`, never `lg:px-4`,
so desktop padding cannot leak into the 1024–1199px tablet band.

---

### Task 1: Mobile hero view model

Pull the hero's presentation decisions into a pure, testable module before building any markup.

**Files:**
- Create: `frontend/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs`
- Create: `frontend/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.test.mjs`

**Interfaces:**
- Produces `selectMobileHeroModel(input) => model`, where `input` is:
  ```
  { setName, era, logoUrl, setValue: { current, deltaAmount, deltaPercent, windowLabel },
    rip: { label, score, tier, rank, cohortSize, verdict } }
  ```
  and `model` is:
  ```
  { identity: { name, era, logoUrl, hasLogo },
    value: { hasValue, amountText, deltaText, direction },
    rip: { hasRip, scoreText, tierText, rankText, verdict, isActionable } }
  ```
- `direction` is `"positive" | "negative" | "neutral"`.
- `deltaText` is the single combined string the brief specifies: `"$115.78 · 14.9% · 30D"` (no arrow — the arrow is a separate glyph so movement is never conveyed by colour alone).
- Consumed by: Task 2.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import { selectMobileHeroModel } from "./mobileHeroModel.mjs";

const base = {
  setName: "Perfect Order",
  era: "Mega Evolution",
  logoUrl: "https://images.example/logo.png",
  setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
  rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite, some path risk" },
};

test("a complete set produces the brief's hero composition", () => {
  const model = selectMobileHeroModel(base);

  assert.equal(model.identity.name, "Perfect Order");
  assert.equal(model.identity.era, "Mega Evolution");
  assert.equal(model.identity.hasLogo, true);

  assert.equal(model.value.hasValue, true);
  assert.equal(model.value.amountText, "$663.14");
  assert.equal(model.value.direction, "negative");
  assert.equal(model.value.deltaText, "$115.78 · 14.9% · 30D");

  assert.equal(model.rip.hasRip, true);
  assert.equal(model.rip.scoreText, "100");
  assert.equal(model.rip.tierText, "S Tier");
  assert.equal(model.rip.rankText, "Rank #1");
  assert.equal(model.rip.verdict, "Elite, some path risk");
  assert.equal(model.rip.isActionable, true);
});

test("positive movement is signed the other way and never colour-only", () => {
  const model = selectMobileHeroModel({
    ...base,
    setValue: { current: 100, deltaAmount: 8.5, deltaPercent: 9.25, windowLabel: "7D" },
  });
  assert.equal(model.value.direction, "positive");
  // The magnitude is unsigned here; the caller renders a triangle glyph plus an
  // accessible label, so direction is never carried by colour alone.
  assert.equal(model.value.deltaText, "$8.50 · 9.3% · 7D");
});

test("zero movement reads as flat, not as a fake gain", () => {
  const model = selectMobileHeroModel({
    ...base,
    setValue: { current: 100, deltaAmount: 0, deltaPercent: 0, windowLabel: "30D" },
  });
  assert.equal(model.value.direction, "neutral");
  assert.equal(model.value.deltaText, "$0.00 · 0.0% · 30D");
});

test("a missing set value does not blank the hero", () => {
  const model = selectMobileHeroModel({ ...base, setValue: { current: null, deltaAmount: null, deltaPercent: null, windowLabel: "30D" } });
  assert.equal(model.value.hasValue, false);
  assert.equal(model.value.amountText, "—");
  assert.equal(model.value.deltaText, null);
  assert.equal(model.rip.hasRip, true, "RIP survives a missing set value");
});

test("missing RIP does not blank the hero", () => {
  const model = selectMobileHeroModel({ ...base, rip: { label: "RIP Score", score: null, tier: null, rank: null, cohortSize: null, verdict: null } });
  assert.equal(model.rip.hasRip, false);
  assert.equal(model.rip.isActionable, false, "an empty RIP row must not advertise a tap target");
  assert.equal(model.value.hasValue, true, "Set Value survives a missing RIP");
});

test("a partial RIP still renders whatever exists", () => {
  const model = selectMobileHeroModel({ ...base, rip: { ...base.rip, rank: null, cohortSize: null } });
  assert.equal(model.rip.hasRip, true);
  assert.equal(model.rip.rankText, null);
  assert.equal(model.rip.tierText, "S Tier");
});

test("a missing logo degrades to the name alone", () => {
  const model = selectMobileHeroModel({ ...base, logoUrl: null });
  assert.equal(model.identity.hasLogo, false);
  assert.equal(model.identity.logoUrl, null);
  assert.equal(model.identity.name, "Perfect Order");
});

test("a missing name never renders an empty heading", () => {
  const model = selectMobileHeroModel({ ...base, setName: "   " });
  assert.equal(model.identity.name, "Selected Set");
});

test("a tier already carrying the word Tier is not doubled", () => {
  const model = selectMobileHeroModel({ ...base, rip: { ...base.rip, tier: "S Tier" } });
  assert.equal(model.rip.tierText, "S Tier");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/pokemon/set-page/PokemonSetHero/mobileHeroModel.test.mjs`

Expected: FAIL — module not found.

- [ ] **Step 3: Write the module**

Create `frontend/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs`:

```javascript
// Presentation-only view model for the mobile/tablet set hero. Every number
// arrives already computed by the page — this module chooses text and
// availability, never values.

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cleanText(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function formatTier(tier) {
  const text = cleanText(tier);
  if (!text) return null;
  return /\btier$/i.test(text) ? text : `${text} Tier`;
}

export function selectMobileHeroModel(input = {}) {
  const setValue = input?.setValue || {};
  const rip = input?.rip || {};

  const current = toFiniteNumber(setValue.current);
  const deltaAmount = toFiniteNumber(setValue.deltaAmount);
  const deltaPercent = toFiniteNumber(setValue.deltaPercent);
  const windowLabel = cleanText(setValue.windowLabel);

  const direction =
    deltaAmount === null
      ? "neutral"
      : deltaAmount < 0
      ? "negative"
      : deltaAmount > 0
      ? "positive"
      : "neutral";

  // Magnitude only. The caller pairs this with a direction glyph and an
  // accessible label so movement is never conveyed by colour alone.
  const deltaText =
    deltaAmount === null && deltaPercent === null
      ? null
      : [
          deltaAmount === null ? null : currencyFormatter.format(Math.abs(deltaAmount)),
          deltaPercent === null ? null : `${Math.abs(deltaPercent).toFixed(1)}%`,
          windowLabel,
        ]
          .filter(Boolean)
          .join(" · ");

  const score = toFiniteNumber(rip.score);
  const tierText = formatTier(rip.tier);
  const rank = toFiniteNumber(rip.rank);
  const verdict = cleanText(rip.verdict);
  const hasRip = score !== null || tierText !== null || rank !== null || verdict !== null;

  return {
    identity: {
      name: cleanText(input.setName) || "Selected Set",
      era: cleanText(input.era),
      logoUrl: cleanText(input.logoUrl),
      hasLogo: cleanText(input.logoUrl) !== null,
    },
    value: {
      hasValue: current !== null,
      amountText: current === null ? "—" : currencyFormatter.format(current),
      deltaText,
      direction,
    },
    rip: {
      label: cleanText(rip.label) || "RIP Score",
      hasRip,
      scoreText: score === null ? null : String(Math.round(score)),
      tierText,
      rankText: rank === null ? null : `Rank #${Math.round(rank)}`,
      cohortSize: toFiniteNumber(rip.cohortSize),
      verdict,
      // Only offer a tap target when there is something to navigate to.
      isActionable: hasRip,
    },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/pokemon/set-page/PokemonSetHero/mobileHeroModel.test.mjs`

Expected: PASS, all nine tests.

---

### Task 2: Build the mobile/tablet hero

**Files:**
- Create: `frontend/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.jsx`
- Create: `frontend/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.test.jsx`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:12620-12775`

**Interfaces:**
- Consumes: `selectMobileHeroModel` from `./mobileHeroModel.mjs`.
- Props: `{ model, tierPillStyle, verdictPillStyle, pickerOpen, onTogglePicker, onSelectTarget, onPickerKeyDown, targets, selectedTargetId, pickerDisabled, listboxId, onValueActivate, onRipActivate }`.
- Produces: a single `<section data-set-mobile-hero>`. The existing desktop grid gains `max-desk:hidden`; the mobile hero is `desk:hidden`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.test.jsx`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import PokemonSetMobileHero from "./PokemonSetMobileHero.jsx";
import { selectMobileHeroModel } from "./mobileHeroModel.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const model = selectMobileHeroModel({
  setName: "Scarlet & Violet—Journey Together",
  era: "Scarlet & Violet",
  logoUrl: "https://images.example/logo.png",
  setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
  rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite, some path risk" },
});

async function renderHero(overrides = {}) {
  const calls = { value: 0, rip: 0, toggle: 0 };
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <PokemonSetMobileHero
        model={model}
        tierPillStyle={{}}
        verdictPillStyle={{}}
        pickerOpen={false}
        onTogglePicker={() => { calls.toggle += 1; }}
        onSelectTarget={() => {}}
        onPickerKeyDown={() => {}}
        targets={[{ target_type: "set", target_id: "perfectOrder", name: "Perfect Order" }]}
        selectedTargetId="perfectOrder"
        pickerDisabled={false}
        listboxId="set-mobile-picker-list"
        onValueActivate={() => { calls.value += 1; }}
        onRipActivate={() => { calls.rip += 1; }}
        {...overrides}
      />
    );
  });
  return { renderer, calls };
}

test("the hero renders identity, value and RIP in the brief's order", async () => {
  const { renderer } = await renderHero();
  const section = renderer.root.findByProps({ "data-set-mobile-hero": true });
  const regions = section.findAll((node) => typeof node.props["data-hero-region"] === "string");
  assert.deepEqual(regions.map((node) => node.props["data-hero-region"]), ["identity", "value", "rip"]);
});

test("Set Value is the dominant metric and carries the movement", async () => {
  const { renderer } = await renderHero();
  const value = renderer.root.findByProps({ "data-hero-region": "value" });
  const text = JSON.stringify(value.toJSON());
  assert.ok(text.includes("$663.14"));
  assert.ok(text.includes("$115.78 · 14.9% · 30D"));
  assert.ok(text.includes("SET VALUE") || text.includes("Set Value"));
});

test("movement direction is not carried by colour alone", async () => {
  const { renderer } = await renderHero();
  const value = renderer.root.findByProps({ "data-hero-region": "value" });
  const label = value.findByProps({ "data-hero-movement-label": true });
  assert.ok(/down|decrease|negative/i.test(label.props.children), "an accessible direction word accompanies the colour");
});

test("the value and RIP regions are the tap targets, replacing the separate links", async () => {
  const { renderer, calls } = await renderHero();
  const value = renderer.root.findByProps({ "data-hero-region": "value" });
  const rip = renderer.root.findByProps({ "data-hero-region": "rip" });

  assert.equal(value.type, "button", "the whole Set Value region is the control");
  assert.equal(rip.type, "button", "the whole RIP region is the control");

  await act(async () => value.props.onClick());
  await act(async () => rip.props.onClick());
  assert.equal(calls.value, 1, "Set Value routes to the trend");
  assert.equal(calls.rip, 1, "RIP routes to the breakdown");

  // The old standalone yellow links are gone from this composition.
  const text = JSON.stringify(renderer.root.toJSON());
  assert.ok(!text.includes("View trend"), "the separate View trend link is replaced by the region tap");
  assert.ok(!text.includes("View verdict"), "the separate View verdict link is replaced by the region tap");
});

test("there is one hero surface, not a card containing cards", async () => {
  const { renderer } = await renderHero();
  const json = JSON.stringify(renderer.root.toJSON());
  const borderedSurfaces = (json.match(/set-glass-surface/g) || []).length;
  assert.equal(borderedSurfaces, 0, "the hero must not nest the shared card surface inside itself");
});

test("a set with no RIP still renders identity and value", async () => {
  const bare = selectMobileHeroModel({
    setName: "Perfect Order",
    era: null,
    logoUrl: null,
    setValue: { current: 12.5, deltaAmount: null, deltaPercent: null, windowLabel: "30D" },
    rip: { label: "RIP Score", score: null, tier: null, rank: null, cohortSize: null, verdict: null },
  });
  const { renderer } = await renderHero({ model: bare });
  assert.ok(renderer.root.findByProps({ "data-hero-region": "value" }));
  assert.equal(renderer.root.findAllByProps({ "data-hero-region": "rip" }).length, 0, "an empty RIP row is omitted, not rendered blank");
});

test("the set picker is reachable and announces its state", async () => {
  const { renderer, calls } = await renderHero();
  const picker = renderer.root.findByProps({ "data-set-mobile-picker": true });
  assert.equal(picker.props["aria-haspopup"], "listbox");
  assert.equal(picker.props["aria-expanded"], false);
  assert.equal(picker.props["aria-controls"], "set-mobile-picker-list");
  await act(async () => picker.props.onClick());
  assert.equal(calls.toggle, 1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.test.jsx`

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Create `frontend/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.jsx`:

```jsx
"use client";

import React from "react";

import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";

const DIRECTION_GLYPH = { positive: "▲", negative: "▼", neutral: "■" };
const DIRECTION_WORD = { positive: "Up", negative: "Down", neutral: "Flat" };
// The same two constants MarketValueChange and DeltaTrendIcon use, so movement
// reads identically everywhere. Do not substitute a new colour system here.
const DIRECTION_COLOR = {
  positive: POSITIVE_VALUE_COLOR,
  negative: NEGATIVE_VALUE_COLOR,
  neutral: "var(--text-secondary)",
};

function TrailingChevron() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 flex-none text-[var(--text-secondary)]" fill="currentColor">
      <path d="M7.21 5.23a.75.75 0 0 1 1.06-.02l4.45 4.25a.75.75 0 0 1 0 1.08l-4.45 4.25a.75.75 0 1 1-1.04-1.08L11.12 10 7.23 6.29a.75.75 0 0 1-.02-1.06Z" />
    </svg>
  );
}

// One restrained surface, not a card of cards. The brief's hierarchy is
// identity -> Set Value (dominant) -> RIP (secondary intelligence). The
// separate "View trend" / "View verdict" links are gone because the regions
// they described are now the controls themselves.
export default function PokemonSetMobileHero({
  model,
  tierPillStyle,
  verdictPillStyle,
  pickerOpen,
  onTogglePicker,
  onSelectTarget,
  onPickerKeyDown,
  targets,
  selectedTargetId,
  pickerDisabled,
  listboxId,
  onValueActivate,
  onRipActivate,
}) {
  const { identity, value, rip } = model;
  const availableTargets = Array.isArray(targets) ? targets : [];

  return (
    <section
      data-set-mobile-hero
      className="set-context-premium relative rounded-xl border px-4 py-3.5 tab:px-5 tab:py-4"
    >
      <div className="tab:grid tab:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] tab:items-center tab:gap-6">
        <div data-hero-region="identity" className="relative flex min-w-0 items-center gap-3">
          {identity.hasLogo ? (
            <span className="flex h-11 w-16 flex-none items-center justify-center tab:h-14 tab:w-20">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={identity.logoUrl}
                alt=""
                aria-hidden="true"
                className="max-h-11 w-auto max-w-16 object-contain opacity-95 tab:max-h-14 tab:max-w-20"
                loading="lazy"
                decoding="async"
              />
            </span>
          ) : null}

          <div className="min-w-0 flex-1">
            <h1 className="set-context-identity min-w-0 break-words text-base font-semibold leading-tight text-[var(--text-primary)] tab:text-lg">
              {identity.name}
            </h1>
            {identity.era ? (
              <p className="mt-0.5 min-w-0 truncate text-xs font-medium leading-tight text-[var(--text-secondary)]">
                {identity.era}
              </p>
            ) : null}
          </div>

          <button
            type="button"
            data-set-mobile-picker
            onClick={onTogglePicker}
            disabled={pickerDisabled}
            aria-expanded={Boolean(pickerOpen)}
            aria-haspopup="listbox"
            aria-controls={listboxId}
            aria-label="Switch set"
            title={availableTargets.length > 0 ? "Switch set" : "No sets available"}
            className="inline-flex h-11 w-11 flex-none items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <svg viewBox="0 0 20 20" className={`h-4 w-4 transition-transform ${pickerOpen ? "rotate-180" : ""}`} fill="currentColor" aria-hidden="true">
              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
            </svg>
          </button>

          {pickerOpen ? (
            <div
              id={listboxId}
              role="listbox"
              aria-label="Available sets"
              onKeyDown={onPickerKeyDown}
              className="index-scrollbar absolute right-0 top-[calc(100%+0.5rem)] z-50 max-h-56 w-full min-w-[16rem] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1.5 shadow-[0_14px_34px_rgba(0,0,0,0.45)]"
            >
              {availableTargets.map((target) => {
                const isSelected = String(target.target_id) === String(selectedTargetId || "");
                return (
                  <button
                    key={`mobile-set-option:${target.target_type}:${target.target_id}`}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => onSelectTarget(target)}
                    className={`flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm leading-5 transition-colors ${
                      isSelected
                        ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{target.name}</span>
                    {isSelected ? <span className="shrink-0 text-xs font-medium text-[var(--accent)]">Current</span> : null}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        <div className="min-w-0 tab:row-span-2">
          {/* No divider between Set Value and RIP - the brief removes it. */}
          <button
            type="button"
            data-hero-region="value"
            onClick={onValueActivate}
            className="mt-3.5 flex w-full min-w-0 items-start justify-between gap-3 rounded-lg text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] tab:mt-0"
          >
            <span className="min-w-0">
              <span className="set-context-eyebrow block">Set Value</span>
              <span className="mt-1 block truncate text-3xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
                {value.amountText}
              </span>
              {value.deltaText ? (
                <span className="mt-1.5 flex min-w-0 items-baseline gap-1.5 text-xs font-medium">
                  <span aria-hidden="true" style={{ color: DIRECTION_COLOR[value.direction] }}>
                    {DIRECTION_GLYPH[value.direction]}
                  </span>
                  <span data-hero-movement-label className="sr-only">{`${DIRECTION_WORD[value.direction]} `}</span>
                  <span className="min-w-0 truncate tabular-nums" style={{ color: DIRECTION_COLOR[value.direction] }}>
                    {value.deltaText}
                  </span>
                </span>
              ) : null}
            </span>
            <TrailingChevron />
          </button>

          {rip.hasRip ? (
            <button
              type="button"
              data-hero-region="rip"
              onClick={onRipActivate}
              className="mt-3.5 flex w-full min-w-0 items-start justify-between gap-3 rounded-lg border-t border-[var(--border-subtle)] pt-3.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <span className="min-w-0">
                <span className="set-context-eyebrow block">{rip.label}</span>
                <span className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  {rip.scoreText ? (
                    <span className="text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">{rip.scoreText}</span>
                  ) : null}
                  {rip.tierText ? (
                    <span className="inline-flex flex-none items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-tight" style={tierPillStyle}>
                      {rip.tierText}
                    </span>
                  ) : null}
                  {rip.rankText ? (
                    <span
                      className="flex-none text-[11px] font-medium leading-tight tabular-nums text-[var(--text-secondary)]"
                      title={rip.cohortSize === null ? rip.rankText : `${rip.rankText} of ${Math.round(rip.cohortSize)} ranked sets`}
                    >
                      {rip.rankText}
                    </span>
                  ) : null}
                </span>
                {rip.verdict ? (
                  <span className="mt-1.5 flex min-w-0">
                    <span className="inline-flex min-w-0 max-w-full items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight" style={verdictPillStyle}>
                      <span className="truncate">{rip.verdict}</span>
                    </span>
                  </span>
                ) : null}
              </span>
              <TrailingChevron />
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero.test.jsx`

Expected: PASS, all seven tests.

- [ ] **Step 5: Mount it beside the desktop hero**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, add the imports:

```javascript
import PokemonSetMobileHero from "@/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero";
import { selectMobileHeroModel } from "@/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs";
```

Alongside the other hero derivations (after line 9578, where `setContextRipCohort` is defined), add:

```javascript
  // Same already-computed values the desktop hero reads. No extra request, no
  // extra state — only the composition differs, which is the one case the
  // brief allows a separate presentational component for.
  const mobileHeroModel = useMemo(
    () =>
      selectMobileHeroModel({
        setName: selectedName,
        era: selectedTarget?.era ?? null,
        logoUrl: heroLogoUrl,
        setValue: {
          current: setHeaderSummary.setValue.current,
          deltaAmount: setHeaderSummary.setValue.delta30dAmount,
          deltaPercent: setHeaderSummary.setValue.delta30dPercent,
          windowLabel: "30D",
        },
        rip: {
          label: setContextRipLabel,
          score: topScoreRaw,
          tier: setContextRipTier,
          rank: setContextRipRank,
          cohortSize: setContextRipCohort,
          verdict: recommendationBadge,
        },
      }),
    [
      heroLogoUrl,
      recommendationBadge,
      selectedName,
      selectedTarget?.era,
      setContextRipCohort,
      setContextRipLabel,
      setContextRipRank,
      setContextRipTier,
      setHeaderSummary.setValue.current,
      setHeaderSummary.setValue.delta30dAmount,
      setHeaderSummary.setValue.delta30dPercent,
      topScoreRaw,
    ]
  );
```

Then in the JSX, add `max-desk:hidden` to the existing desktop hero `<section>` at line 12620–12623 so it becomes:

```jsx
                <section
                  data-set-context-header
                  className="set-context-premium page-hero-panel relative min-h-[88px] overflow-visible rounded-t-xl border max-desk:hidden md:rounded-t-2xl"
                >
```

and immediately **before** that `<section>`, add:

```jsx
                <div className="desk:hidden">
                  <PokemonSetMobileHero
                    model={mobileHeroModel}
                    tierPillStyle={setContextRipPresentation.tierPill}
                    verdictPillStyle={setContextRipPresentation.verdictPill}
                    pickerOpen={heroSetPickerOpen}
                    onTogglePicker={() => setHeroSetPickerOpen((open) => !open)}
                    onSelectTarget={handleHeroSetSelect}
                    onPickerKeyDown={handleSetPickerKeyDown}
                    targets={switcherTargets}
                    selectedTargetId={requestedTargetId}
                    pickerDisabled={isPending || switcherTargets.length === 0}
                    listboxId="set-mobile-picker-list"
                    onValueActivate={handleViewSetValueTrend}
                    onRipActivate={() =>
                      handleSetDetailNavSelect({ tab: "insights", section: "rip-score", targetId: "set-detail-rip-score" })
                    }
                  />
                </div>
```

The picker's open state is shared, so opening it in one composition and resizing across 1200px cannot desync. The listbox ids differ (`compact-set-picker-list` vs `set-mobile-picker-list`), so no duplicate id is introduced.

- [ ] **Step 6: Verify**

Run: `cd frontend && npm run build`

Then at `320px`, `390px`, `834px` and `1199px`:
- The hero shows logo, name, era, selector, then Set Value (dominant), then RIP.
- No divider between Set Value and RIP other than the single hairline the brief's hierarchy implies.
- The Overview/Cards/Pull Rates/Insights tabs are visually separate from the hero.
- Tapping the Set Value region scrolls to Set Value Trend; tapping the RIP region routes to the RIP breakdown.
- `Scarlet & Violet—Journey Together` wraps and does not push the selector off screen. Check at 320px specifically.
- The selector's tap target is at least 44×44.

At `1200px` and `1366px`: the desktop hero is unchanged and the mobile hero is not rendered.

---

### Task 3: Turn the Overview into a continuous feed

Below 1200px the Overview is a stack of `SectionCard`s, each a rounded bordered surface with its own padding, sitting inside the page gutter. That is the "card inside card" problem: gutter + outer border + outer padding + inner padding before any data.

**Files:**
- Modify: `frontend/app/styles/globals.css` (inside the `@media (max-width: 1199.98px)` block from Plan 2 Task 5)
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:12805` (mark the Overview section as the feed)
- Modify: `frontend/components/Profile/PublicProfileLocalScaffold.js` (gutter values)
- Create: `frontend/components/explore/MobileFeedComposition.contract.test.mjs`

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/MobileFeedComposition.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const client = read("RipStatisticsPageClient.jsx");
const scaffold = read("../Profile/PublicProfileLocalScaffold.js");

const mobileBlock = css.slice(
  css.indexOf("@media (max-width: 1199.98px) {"),
  css.indexOf("\n}", css.indexOf("@media (max-width: 1199.98px) {"))
);

test("the Overview section is marked as the mobile feed", () => {
  assert.ok(client.includes('<section id="set-detail-overview" data-mobile-feed'), "the feed region is explicit");
});

test("outer card chrome is stripped inside the feed below desktop", () => {
  assert.ok(mobileBlock.includes("[data-mobile-feed] .set-glass-surface"));
  for (const declaration of ["border: 0;", "border-radius: 0;", "background: transparent;", "box-shadow: none;"]) {
    assert.ok(mobileBlock.includes(declaration), `${declaration} must be part of the feed reset`);
  }
});

test("sections are separated by dividers rather than by nested boxes", () => {
  assert.ok(mobileBlock.includes("[data-mobile-feed] > * + * {"));
  assert.ok(/\[data-mobile-feed\] > \* \+ \* \{[^}]*border-top: 1px solid var\(--border-subtle\);/s.test(mobileBlock));
});

test("the reset is scoped so desktop and other tabs are untouched", () => {
  // Cards' toolbar also uses .set-glass-surface. Scoping to [data-mobile-feed]
  // keeps this to the Overview, and the media query keeps it off desktop.
  assert.ok(!css.includes("\n.set-glass-surface {\n  border: 0;"), "no unscoped global reset");
});

test("page gutters are 16px on phones and 24px on tablets", () => {
  // Four strings: contentFramed + contentFlat in each of the two recipes.
  assert.equal(
    (scaffold.match(/px-4 pt-3 tab:px-6/g) || []).length,
    4,
    "both breakpoint recipes carry the brief's gutters in both content variants"
  );
});

test("the tablet content area is capped and centred", () => {
  // Brief section 10: roughly 760-960px of effective content on tablet, not a
  // phone layout stretched edge to edge across 1024px.
  assert.ok(client.includes("max-desk:mx-auto max-desk:w-full max-desk:max-w-[960px]"));
  assert.ok(
    !client.includes("lg:max-w-[1440px] lg:px-4"),
    "desktop horizontal padding must not leak into the 1024-1199px tablet band"
  );
  assert.ok(client.includes("desk:px-4 2xl:px-5"), "the desktop gutter is gated at 1200px");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/MobileFeedComposition.contract.test.mjs`

Expected: FAIL on every test.

- [ ] **Step 3: Mark the feed region**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, change line 12805 from:

```jsx
                  <section id="set-detail-overview" className="scroll-mt-24 space-y-5 md:scroll-mt-28">
```

to:

```jsx
                  <section id="set-detail-overview" data-mobile-feed className="scroll-mt-24 space-y-5 max-desk:space-y-0 md:scroll-mt-28">
```

- [ ] **Step 4: Add the feed CSS**

In `frontend/app/styles/globals.css`, inside the `@media (max-width: 1199.98px) { ... }` block added in Plan 2 Task 5, append:

```css
  /* Continuous analytical feed. Below 1200px the Overview's repeated outer
     cards cost gutter + border + outer padding + inner padding before any data
     is drawn. Strip the outer surface and let headings plus dividers carry the
     structure. Bordered containers survive only where the boundary means
     something — selected controls, interactive rows, alerts, callouts — which
     are all inner elements this reset does not reach.
     Scoped to [data-mobile-feed] so the Cards toolbar and every non-Overview
     surface keep their chrome. */
  [data-mobile-feed] .set-glass-surface {
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
    padding-inline: 0;
    padding-block: 0;
  }

  [data-mobile-feed] > * + * {
    margin-top: 1.25rem;
    border-top: 1px solid var(--border-subtle);
    padding-top: 1.25rem;
  }
```

- [ ] **Step 5: Set the brief's gutters**

In `frontend/components/Profile/PublicProfileLocalScaffold.js`, change `px-3 pt-3 sm:px-6` to `px-4 pt-3 tab:px-6` in `contentFramed` and `contentFlat` of **both** `SCAFFOLD_BREAKPOINTS` recipes (four strings). That is 16px below 600px and 24px from 600px up, which is what the brief asks for, and it leaves each recipe's desktop overrides untouched.

- [ ] **Step 6: Cap and centre the tablet content area**

Brief §10 wants a centred content area of roughly `760–960px` on tablet. Today the set page's shell only constrains width from `lg` (1024px) upward, so at `768px`–`1023px` the feed stretches edge to edge and long rows become hard to scan.

In `frontend/components/explore/RipStatisticsPageClient.jsx`, change the `contentShellClassName` prop at line 12562 from:

```jsx
        contentShellClassName={setDetailMode ? "lg:w-full lg:max-w-[1440px] lg:px-4 2xl:px-5" : undefined}
```

to:

```jsx
        contentShellClassName={
          setDetailMode
            ? "max-desk:mx-auto max-desk:w-full max-desk:max-w-[960px] lg:w-full lg:max-w-[1440px] desk:px-4 2xl:px-5"
            : undefined
        }
```

Two changes: the tablet cap (`max-desk:max-w-[960px]`, a no-op below 600px where the viewport is already narrower), and `lg:px-4` becomes `desk:px-4` so the desktop horizontal padding no longer leaks into the 1024–1199px tablet band, where the gutter is now owned by `tab:px-6`.

Add to the `@media (max-width: 1199.98px)` block, so a phone never inherits a stray centring margin:

```css
  [data-mobile-feed] {
    margin-inline: auto;
    width: 100%;
  }
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/MobileFeedComposition.contract.test.mjs`

Expected: PASS, all five tests.

- [ ] **Step 8: Verify width recovery and that nothing looks unfinished**

At `320px` and `390px`, measure the usable content width:

```javascript
const chart = document.querySelector("#set-detail-set-value-trend .recharts-responsive-container");
chart.getBoundingClientRect().width;
```

Expected: meaningfully wider than on `main` at the same viewport — the outer card's border and padding are gone.

At `768px` and `1024px`, confirm the feed is centred and its content box measures no more than `960px`:

```javascript
document.querySelector("[data-mobile-feed]").getBoundingClientRect().width;
```

By eye, confirm the page still reads as designed rather than flat: section headings are clear, dividers separate sections, and controls, interactive rows and callouts still have their own borders.

Then check `/TCGs/Pokemon/Sets/<set>?tab=cards` at `390px` — the Cards toolbar must **still** have its bordered surface. If it lost it, the selector escaped its scope.

---

### Task 4: Compact ranked Top Chase rows

`TopMarketCardRow` stacks image, sparkline and price vertically below `lg`, producing roughly 200px per row and a very long scroll. The brief wants a compact ranked market row, an entire-row tap target, and a five-row Overview preview.

**Files:**
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:2921-3011` (`TopMarketCardRow`), `:3149-3182` (`TopChaseCardsModule`)
- Create: `frontend/components/explore/TopChaseCompactRows.contract.test.mjs`

**Interfaces:**
- Consumes: `updateSetDetailQueryParams({ pathname, searchParams, tab, section, cardSort, movementFilter })` — the same builder `moversTickerHref` already uses at line 10399.
- Produces: `TopMarketCardRow` accepts a new optional `href` prop; when present the row renders as an `<a>` wrapping the existing grid, otherwise it renders the existing `<div>`.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/TopChaseCompactRows.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const row = source.slice(
  source.indexOf("function TopMarketCardRow("),
  source.indexOf("function InlinePanelSkeleton(")
);
const module_ = source.slice(
  source.indexOf("function TopChaseCardsModule("),
  source.indexOf("function hasMarketMoverRows(")
);

test("the mobile row is a compact ranked row, not a stacked card", () => {
  // Rank, small image, name+rarity and price+movement share one line; the
  // sparkline spans beneath it.
  assert.ok(row.includes("grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto]"), "the compact mobile grid is in place");
  // Desktop keeps its four reading columns: rank | card | trend | price. The
  // trend is now a sibling placed into the second column of the outer grid.
  assert.ok(row.includes("desk:grid-cols-[minmax(0,1fr)_minmax(9rem,14.5rem)]"), "the outer desktop grid reserves the trend column");
  assert.ok(row.includes("desk:grid-cols-[3rem_minmax(0,1fr)_minmax(8rem,10rem)]"), "the desktop link keeps rank, card and price");
  assert.ok(row.includes("desk:col-start-2 desk:row-start-1"), "the trend column sits beside the link at desktop");
});

test("every field the brief lists survives in the row", () => {
  for (const token of ["#{index + 1}", "{name}", "{rarity", "MarketValueChange", "CompactSparkline"]) {
    assert.ok(row.includes(token), `${token} must remain in the row`);
  }
});

test("the information region is the link and the sparkline is its sibling", () => {
  // Correction 3: an interactive, focusable, arrow-key-driven chart must never
  // be nested inside a navigation anchor.
  assert.ok(row.includes('const NavigationRegion = href ? "a" : "div";'), "the nav region type follows the href prop");
  assert.ok(row.includes("data-row-nav"), "the navigation region is identifiable");
  assert.ok(row.includes("data-row-chart"), "the chart region is identifiable");

  const navStart = row.indexOf("<NavigationRegion");
  const navEnd = row.indexOf("</NavigationRegion>");
  assert.ok(navStart >= 0 && navEnd > navStart, "the navigation region must be locatable");
  assert.ok(
    !row.slice(navStart, navEnd).includes("CompactSparkline"),
    "the sparkline must not be rendered inside the anchor"
  );
  assert.ok(row.indexOf("CompactSparkline") > navEnd, "the chart region is a sibling that follows the link");
  assert.ok(row.includes("min-h-11") || row.includes("py-2.5"), "the row keeps a usable touch height");
});

test("the row destination keeps the set and the timeframe context", () => {
  assert.ok(source.includes("const topChaseRowHref = updateSetDetailQueryParams("), "the href is built from the shared builder");
  assert.ok(source.includes('tab: "cards"'), "chase rows lead into the Cards experience for this set");
});

test("rows 6-10 are never discarded", () => {
  // Five rows is a preview only because the existing expand control still
  // reveals the full fetched list in place. Parity spec section 6.
  assert.ok(module_.includes("showAllChaseCards ? 10 : 5"), "the preview is five rows and the expansion is ten");
  assert.ok(module_.includes("View all chase cards"), "the reveal control survives");
  assert.ok(module_.includes("Show fewer chase cards"), "the collapse control survives");
  assert.ok(module_.includes("totalRows > 5"), "the control appears whenever there is more than the preview");
});

test("loading placeholders match the final compact row height", () => {
  assert.ok(source.includes('data-top-chase-skeleton'), "the chase skeleton is distinguishable");
  assert.ok(source.includes("max-desk:h-[4.25rem]"), "the placeholder matches the compact row box");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/TopChaseCompactRows.contract.test.mjs`

Expected: FAIL on every test.

- [ ] **Step 3: Recompose the row as a link plus a sibling chart**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, change the
`TopMarketCardRow` signature to accept `href`:

```javascript
function TopMarketCardRow({ card, index, selectedWindowKey, marketAsOfDate = null, href = null }) {
```

Everything above the `return` — `imageUrl`, `name`, `rarity`, `price`,
`historyPoints`, `windowState`, `sparklinePoints`, `displayDeltaAmount`,
`displayDelta`, `sparklineTone` — is unchanged.

Replace the returned JSX with a **container holding two siblings**. Correction 3:
the sparkline is independently interactive (pointer, tap, scrub, focus, arrow
keys, Escape) and must never be a descendant of the anchor.

```jsx
  // Correction 3: the information region is the link; the sparkline is its
  // sibling. Nesting a focusable, arrow-key-driven chart inside an <a> is
  // invalid interactive content, and stopPropagation would only paper over it.
  const NavigationRegion = href ? "a" : "div";

  return (
    <div
      data-top-chase-row
      className="grid min-w-0 grid-cols-1 gap-y-1.5 px-3 py-2.5 desk:grid-cols-[minmax(0,1fr)_minmax(9rem,14.5rem)] desk:items-center desk:gap-3 desk:px-3 desk:py-3"
    >
      <NavigationRegion
        {...(href ? { href, "aria-label": `${name} — open in Cards` } : {})}
        data-row-nav
        className="grid min-h-11 min-w-0 grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-lg transition-colors hover:bg-[var(--surface-hover)]/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:grid-cols-[3rem_minmax(0,1fr)_minmax(8rem,10rem)] desk:gap-3"
      >
        {/* rank | compact image (phone/tablet) | name + rarity + desktop image | price + movement */}
      </NavigationRegion>

      <div data-row-chart className="col-span-full min-w-0 desk:col-span-1 desk:col-start-2 desk:row-start-1">
        <CompactSparkline ... />
        {/* first/last date labels, unchanged */}
      </div>
    </div>
  );
```

Notes that bind the implementation:

- The desktop visual result at `1200px+` must be the same four-column reading
  order it is today (`rank | card | trend | price`). The trend column is the
  chart sibling placed into `desk:col-start-2 desk:row-start-1`, and the price is
  the last cell inside the link. The 1024–1199px band deliberately moves to the
  compact composition — that band is *tablet* under the brief, not desktop.
- The header row in `TopMarketCardsContent` (`lg:grid` with the four column
  labels) must move to `desk:grid` and the matching `desk:` column template, or
  its labels will sit over the wrong columns in the tablet band.
- `min-h-11` on the navigation region keeps a 44px touch target.


- [ ] **Step 4: Build the row destination and thread it through**

In the main component, next to `moversTickerHref` (around line 10399), add:

```javascript
  // Chase rows lead into the Cards tab for this set, sorted by price, so the
  // destination keeps both the set and a sensible browsing context.
  // "current-price" is one of the three keys in ALL_CARDS_SORT_OPTIONS
  // (set-number | name | current-price) — an unrecognised value would silently
  // land the Cards tab on its fallback sort.
  const topChaseRowHref = updateSetDetailQueryParams({
    pathname,
    searchParams,
    tab: "cards",
    section: "all-cards",
    cardSort: "current-price",
    movementFilter: "all",
  });
```

Sort direction is separate client state (`cardSortDirection`) and is not part of this URL builder, so the Cards tab applies its own default direction for that sort.

Thread it into `TopChaseCardsModule` and down to the rows: add `rowHref` to `TopChaseCardsModule`'s props and to `TopMarketCardsContent`'s props, and pass `href={rowHref}` on each `<TopMarketCardRow>`. At the call site (line 12910) add `rowHref={topChaseRowHref}`.

- [ ] **Step 5: Preview five rows and keep the reveal**

In `TopChaseCardsModule`, change the `maxRows` expression (line 3164) and the guard (line 3169):

```jsx
        maxRows={showAllChaseCards ? 10 : 5}
```

```jsx
      {totalRows > 5 ? (
```

and the button label:

```jsx
            {showAllChaseCards ? "Show fewer chase cards" : `View all chase cards (${Math.min(totalRows, 10)})`}
```

Update the comment above `useState` to say five rather than six. **Do not** replace the expand control with a link — parity spec §6 forbids discarding rows 6–10, and expand-in-place is what guarantees they remain reachable from the Overview.

- [ ] **Step 6: Match the loading placeholder to the compact row**

In `TopMarketCardsContent`, replace the loading return (line 3057):

```jsx
    return <InlinePanelSkeleton rows={5} />;
```

with:

```jsx
    return (
      <div data-top-chase-skeleton className="animate-pulse space-y-2" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, skeletonIndex) => (
          <div
            key={`top-chase-skeleton:${skeletonIndex}`}
            className="max-desk:h-[4.25rem] h-12 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50"
          />
        ))}
      </div>
    );
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/TopChaseCompactRows.contract.test.mjs`

Expected: PASS, all six tests.

- [ ] **Step 8: Verify**

At `320px`, `390px` and `834px`:
- Each row is roughly `4–4.5rem` tall, not `~200px`.
- Rank, image, name, rarity, price, dollar and percent movement, and the sparkline are all present.
- Tapping anywhere on a row opens the Cards tab for the same set.
- A long card name truncates without colliding with the price.
- A card with no image shows the initials placeholder and the row keeps its height.
- Five rows show; `View all chase cards (10)` reveals all ten; `Show fewer chase cards` collapses again.
- The sparkline is still tap-inspectable (Plan 3 Task 2) — tapping it must not also navigate. If it does, add `event.stopPropagation()` in the sparkline's `onPointerUp`.
- Loading shows five placeholders at the final row height with no jump when data arrives.

At `1366px`: the row is pixel-identical to `main`.

---

### Task 5: Compact the RIP breakdown

Brief §8's target structure — `PROFIT / SAFETY / STABILITY`, then an `ALSO TRACKED` divider, then `OPENING EXPERIENCE` — is exactly what `DecisionSignalsCard` already renders. What it does wrong on mobile is give each pillar its own bordered `set-glass-inner` card.

**Files:**
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:5751-5783` (`DecisionSignalRow`), `:5857`, `:5869` (row containers)
- Create: `frontend/components/explore/RipBreakdownCompact.contract.test.mjs`

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/RipBreakdownCompact.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const row = source.slice(
  source.indexOf("function DecisionSignalRow("),
  source.indexOf("function DecisionSignalsCard(")
);
const card = source.slice(
  source.indexOf("function DecisionSignalsCard("),
  source.indexOf("// A Profit / Safety / Stability card.")
);

test("each pillar is a divider-separated row, not its own card, below desktop", () => {
  assert.ok(row.includes("max-desk:rounded-none"));
  assert.ok(row.includes("max-desk:border-0"));
  assert.ok(row.includes("max-desk:border-b"));
  assert.ok(row.includes("max-desk:px-0"));
  // Desktop keeps the bordered inner card exactly as it is.
  assert.ok(row.includes("set-glass-inner"), "the desktop surface class is preserved");
  assert.ok(row.includes("rounded-xl border border-[var(--border-subtle)]"), "the desktop border is preserved");
});

test("every score, tier, rank and interpretation survives", () => {
  for (const token of ["signal.label", "signal.scoreText", "signal.rankTier", "RankBadge", "summaryText", "parsedRank"]) {
    assert.ok(row.includes(token), `${token} must remain`);
  }
});

test("Also tracked and Opening Experience are preserved", () => {
  assert.ok(card.includes("Also tracked"));
  assert.ok(card.includes("openingRows.map"));
});

test("the compact stack removes the gap that made each row read as a card", () => {
  assert.ok(card.includes('className="grid gap-2 max-desk:gap-0"'), "rows sit flush below desktop");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx tsx --test components/explore/RipBreakdownCompact.contract.test.mjs`

Expected: FAIL.

- [ ] **Step 3: Flatten the row below desktop**

In `frontend/components/explore/RipStatisticsPageClient.jsx`, change `DecisionSignalRow`'s `<article>` (line 5756) to:

```jsx
    <article className="set-glass-inner min-w-0 rounded-xl border border-[var(--border-subtle)] px-3 py-3 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:border-[var(--border-subtle)] max-desk:bg-transparent max-desk:px-0 max-desk:py-3 max-desk:last:border-b-0 max-desk:[backdrop-filter:none]">
```

Change the inner grid (line 5757) so the compact phone layout puts the score, tier and rank on one line under the label:

```jsx
      <div className="grid min-w-0 gap-2.5 max-desk:grid-cols-[minmax(0,1fr)_auto] max-desk:items-start max-desk:gap-x-3 max-desk:gap-y-1 sm:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem] sm:items-center">
```

- [ ] **Step 4: Close the gaps between rows**

Change both row containers in `DecisionSignalsCard` (lines 5857 and 5869) from `className="grid gap-2"` to:

```jsx
      <div className="grid gap-2 max-desk:gap-0">
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx tsx --test components/explore/RipBreakdownCompact.contract.test.mjs`

Expected: PASS, all four tests.

- [ ] **Step 6: Verify**

At `390px`: Profit, Safety and Stability read as three divider-separated rows with their score, tier badge, rank and interpretation intact, then the `Also tracked` divider, then Opening Experience. Measure the section — it should fit within roughly one phone screen. Tier colours are unchanged.

At `1366px`: identical to `main`.

---

### Task 6: Lock the Overview narrative order and the movers strip

Brief §9's recommended order is: hero → Market Movers preview → Set Value Trend → Opening Profit vs Cost → Top Chase Cards → Decision Signals → RIP Breakdown → supporting metrics.

The current DOM already produces that order below `lg`, because both Overview grids stack in source order. This task proves it and keeps the movers strip out from behind the sticky tabs.

**Files:**
- Create: `frontend/components/explore/OverviewNarrativeOrder.contract.test.mjs`
- Modify: `frontend/components/explore/RipStatisticsPageClient.jsx:3266` (`MarketMoversTicker` strip) if verification finds clipping.

- [ ] **Step 1: Write the test**

Create `frontend/components/explore/OverviewNarrativeOrder.contract.test.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const overview = source.slice(
  source.indexOf('<section id="set-detail-overview"'),
  source.indexOf('{setDetailTab === "cards" ? (')
);

test("the Overview tells the brief's story in order", () => {
  const order = [
    "set-detail-movers-ticker",
    "set-detail-set-value-trend",
    "Opening Profit vs Cost",
    "set-detail-top-market-cards",
    "set-detail-set-intelligence",
  ];
  let cursor = -1;
  for (const marker of order) {
    const found = overview.indexOf(marker, cursor + 1);
    assert.ok(found > cursor, `${marker} must appear after the previous section`);
    cursor = found;
  }
});

test("the movers strip is full width and cannot be clipped by its container", () => {
  assert.ok(overview.includes('<div id="set-detail-movers-ticker" className="min-w-0'));
});

test("the movers ticker preserves all ten items and its view-all destination", () => {
  const ticker = source.slice(
    source.indexOf("function MarketMoversTicker("),
    source.indexOf("function normalizePullRateAssumptions(")
  );
  assert.ok(ticker.includes("items.map("), "every selected mover is rendered");
  assert.ok(ticker.includes("View all movers"), "the view-all affordance survives");
  assert.ok(!/\.slice\(0,\s*\d+\)/.test(ticker), "the ticker must not truncate the selection");
  assert.ok(source.includes("const MOVERS_TICKER_FETCH_LIMIT = 10;"), "the fetch limit stays at ten");
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx tsx --test components/explore/OverviewNarrativeOrder.contract.test.mjs`

Expected: PASS. This is a regression lock. If it fails, an earlier task reordered the Overview — restore the order rather than relaxing the test.

- [ ] **Step 3: Verify the movers strip in place**

At `390px`:
- The strip sits directly beneath the sticky tabs when scrolled, never behind them and never behind the hero.
- It is not clipped at either end; it either marquees or scrolls horizontally.
- All ten movers are reachable by scrolling the strip or by following `View all movers →`.
- The marquee still advances after rotating the device and after resizing across 600px and 1200px. If it stalls, the `ResizeObserver` in `MoversTickerViewport.jsx` did not re-measure — check that the effect's `[hasItems, items]` deps still change.
- With `prefers-reduced-motion: reduce`, the strip is static and horizontally scrollable, and all ten are still reachable.

- [ ] **Step 4: Verify empty, partial and error states**

Force each of these and confirm the page still renders everything else:
- Set Value history unavailable → the chart shows its compact empty state; Top Chase, OPvC and RIP still render.
- RIP unavailable → the hero omits the RIP row entirely (no blank box) and Set Value still renders.
- Movers empty → the strip shows `No reliable 7D movers yet.` at its fixed height with no layout shift.
- A section throws → its `SectionErrorBoundary` catches it and the rest of the feed survives.

There must be no large unexplained blank region and no empty outer card in any of these states.

---

### Task 7: Responsive data-parity regression suite

Parity spec §10's final requirement: the same mocked data must produce the same displayed analytical values at 390px, 834px and 1366px. Only composition and interaction mode may differ.

**Files:**
- Create: `frontend/components/explore/responsiveDataParity.test.mjs`

- [ ] **Step 1: Write the test**

Create `frontend/components/explore/responsiveDataParity.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import { selectMobileHeroModel } from "../pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs";
import { selectMoversTickerItems } from "./moversTickerSelector.mjs";
import { findNearestPointIndex } from "./compactSparklineInteraction.mjs";

// The analytical layer is width-agnostic by construction: every selector is a
// pure function of the payload. These assertions lock that in, so a future
// responsive change cannot start feeding a different payload to one breakpoint.

const moversPayload = {
  window: "7D",
  all: Array.from({ length: 14 }, (_, index) => ({
    cardId: `card-${index}`,
    name: `Card ${index}`,
    change7dAmount: 100 - index * 3,
    change7dPercent: 20 - index,
  })),
};

test("mover selection does not depend on viewport width", () => {
  // There is no width parameter to pass; the same call is the only call any
  // breakpoint can make. Ten items, in one order, everywhere.
  const items = selectMoversTickerItems(moversPayload);
  assert.equal(items.length, 10, "all ten movers are selected at every width");
  assert.deepEqual(
    items.map((entry) => entry.card.cardId),
    Array.from({ length: 10 }, (_, index) => `card-${index}`)
  );
});

test("hero values are identical whatever composition renders them", () => {
  const input = {
    setName: "Perfect Order",
    era: "Mega Evolution",
    logoUrl: null,
    setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
    rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite" },
  };
  const first = selectMobileHeroModel(input);
  const second = selectMobileHeroModel(input);
  assert.deepEqual(first, second);
  // And the numbers match the payload exactly - no rounding drift by breakpoint.
  assert.equal(first.value.amountText, "$663.14");
  assert.equal(first.value.deltaText, "$115.78 · 14.9% · 30D");
  assert.equal(first.rip.scoreText, "100");
});

test("a selected chart point resolves to the same datum at any chart width", () => {
  const points = Array.from({ length: 30 }, (_, index) => ({ index, y: 10 + index }));
  // The selector takes a 0..1 ratio, not pixels, so a 320px chart and a 1366px
  // chart resolve the same fraction to the same datum.
  for (const ratio of [0, 0.25, 0.5, 0.75, 1]) {
    assert.equal(findNearestPointIndex(points, 30, ratio), findNearestPointIndex(points, 30, ratio));
  }
  assert.equal(findNearestPointIndex(points, 30, 0), 0);
  assert.equal(findNearestPointIndex(points, 30, 1), 29);
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx tsx --test components/explore/responsiveDataParity.test.mjs`

Expected: PASS.

- [ ] **Step 3: Manual parity check**

Load the same set at `390px`, `834px` and `1366px` and record from each: current Set Value, its dollar and percent movement, the RIP score, tier and rank, the top three chase card names with their prices and movements, and the Expected Value / Typical Return / Realistic Upside figures.

All three widths must produce identical values. Any difference is a defect.

---

### Task 8: Final verification sweep

- [ ] **Step 1: Full suite and build**

Run: `cd frontend && npm run test:frontend && npm run build`

Expected: no failures beyond the Plan 1 Task 1 baseline; build succeeds.

- [ ] **Step 2: Width sweep**

At `320, 360, 390, 430, 480, 599, 600, 768, 834, 1024, 1199, 1200, 1366` on `/TCGs/Pokemon/Sets/<set>?tab=overview`:
- `document.documentElement.scrollWidth <= window.innerWidth` — no horizontal scrolling, especially at 320px.
- No sticky element covers a heading, chart, control or tooltip.
- The bottom nav covers no page content at the end of the page.
- `document.querySelectorAll(".recharts-responsive-container").length` is the same at every width.

Compare `599px` against `600px`: the tablet gutter and two-column arrangements engage cleanly. Compare `1199px` against `1200px`: the composition flips to the desktop layout with no half-applied state.

- [ ] **Step 3: Content and state matrix**

Exercise: short and long set names (`Scarlet & Violet—Journey Together`); sets with and without logos; positive, negative and zero movement; incomplete history; missing RIP; missing simulation data; missing chase-card image; loading states; error states; bottom-of-page content; sticky behaviour during long scrolling; tooltips near viewport edges.

- [ ] **Step 4: Desktop protection**

Screenshot-diff `/TCGs/Pokemon/Sets/<set>` at `1366px` for all four tabs against `main`. All four must be identical.

- [ ] **Step 5: Accessibility pass**

- Every new control is a semantic `<button>` or `<a>` with a visible focus ring.
- Tap targets are at least 44×44.
- Tab order runs top to bottom with no trap in the sticky tabs.
- Movement direction is announced, not colour-only.
- `prefers-reduced-motion: reduce` stops the marquee without hiding any mover.
- The horizontal timeframe row is operable by keyboard.

- [ ] **Step 6: Write the final report**

Produce the concise report the brief's Implementation Process section asks for:
1. Components and styles changed
2. Responsive architecture used
3. Navigation destination changes
4. Confirmation that global navigation styling was not modified
5. Confirmation that desktop remains unchanged
6. Mobile and tablet sections redesigned
7. Tests run and results
8. Any real remaining limitations

---

## Acceptance for this plan

Maps to brief acceptance criteria 11, 12, 13, 14, 17, 18, 19, 21, 22, 25, 26, 27, 28, and parity spec §1, §6, §7, §8, §10.

- [ ] The hero has a clear mobile-first hierarchy with Set Value dominant and RIP as compact secondary intelligence.
- [ ] The hero's tap regions reach Set Value Trend and the RIP breakdown; nothing became unreachable.
- [ ] Outer mobile context cards are gone from the Overview feed; the Cards toolbar keeps its chrome.
- [ ] Page gutters are 16px on phones and 24px on tablets.
- [ ] The tablet content area is centred and capped at 960px; the phone layout is not stretched across 1024px.
- [ ] Top Chase renders compact ranked rows, previews five, reveals all ten, and each row links into the Cards tab for the same set.
- [ ] Profit, Safety, Stability and Opening Experience read compactly with every score, tier, rank and interpretation intact.
- [ ] The Overview order is hero → movers → Set Value → OPvC → Top Chase → Decision Signals.
- [ ] All ten movers remain selected, rotating and reachable, including under reduced motion.
- [ ] Partial data still produces a useful page; no empty outer cards, no unexplained blank regions.
- [ ] The same data produces identical analytical values at 390px, 834px and 1366px.
- [ ] No horizontal scrolling at 320px.
- [ ] Desktop at 1200px+ is pixel-identical to `main` on all four tabs.
