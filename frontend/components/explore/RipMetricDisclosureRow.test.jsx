// The shared RIP disclosure primitive, tested by RENDERING it.
//
// The row has no viewport dependency and no "@/" imports, so it can be mounted
// directly and its real tree inspected. That matters here: every requirement
// below is about what a reader and a screen reader actually get — is the
// supporting metric reachable, is `aria-expanded` truthful, does the disclaimer
// survive a collapse — and none of those are honestly answered by checking that
// a class name appears in the source.
//
// The open-set POLICY (mobile single-open, desktop multi-open) is a decision
// rather than a rendering, and lives in ripDisclosurePolicy.mjs; it is tested
// as a decision at the bottom of this file.

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import RipMetricDisclosureRow from "./RipMetricDisclosureRow.jsx";
import { resolveNextOpenKeys } from "./ripDisclosurePolicy.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const METRICS = [
  { label: "Chance to recover cost", value: "38.4%" },
  { label: "Approximate odds", value: "1 in 2.6" },
  { label: "Pack price used", value: "$4.49" },
];

function render(props) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(RipMetricDisclosureRow, {
        rowKey: "trueWinFrequency",
        title: "Chance to Win",
        value: "72.1",
        valueSuffix: "/100",
        meta: "Rank #3 of 21",
        tier: "A",
        interpretation: "How often a pack comes back worth at least what it cost.",
        metrics: METRICS,
        ...props,
      })
    );
  });
  return renderer;
}

function textOf(node) {
  const collected = [];
  const walk = (value) => {
    if (value === null || value === undefined || value === false) return;
    if (typeof value === "string" || typeof value === "number") {
      collected.push(String(value));
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    walk(value.children);
  };
  walk(node);
  return collected.join(" ");
}

const findAll = (renderer, type) => renderer.root.findAllByType(type);

/* ------------------------------------------------------- default state --- */

test("the collapsed row shows label, value, tier/rank and one explanation", () => {
  const text = textOf(render({ isOpen: false }).toJSON());

  assert.ok(text.includes("Chance to Win"), "label");
  assert.ok(text.includes("72.1"), "score");
  assert.ok(text.includes("/100"), "scale");
  assert.ok(text.includes("Rank #3 of 21"), "rank");
  assert.ok(text.includes("A"), "tier pill");
  assert.ok(text.includes("How often a pack comes back worth at least what it cost."), "explanation");
});

test("supporting metrics are hidden by default and revealed by the disclosure", () => {
  const collapsed = textOf(render({ isOpen: false }).toJSON());
  for (const metric of METRICS) {
    assert.ok(!collapsed.includes(metric.label), `${metric.label} must not be visible by default`);
    assert.ok(!collapsed.includes(metric.value), `${metric.value} must not be visible by default`);
  }

  const expanded = textOf(render({ isOpen: true }).toJSON());
  for (const metric of METRICS) {
    assert.ok(expanded.includes(metric.label), `${metric.label} must be reachable through disclosure`);
    assert.ok(expanded.includes(metric.value), `${metric.value} must be reachable through disclosure`);
  }
});

test("a row with no supporting metrics renders no disclosure control at all", () => {
  // Roster Desirability is exactly this case. An inert control that opens an
  // empty panel would be worse than no control.
  const renderer = render({ metrics: [], isOpen: false });
  assert.equal(findAll(renderer, "button").length, 0);
});

/* ------------------------------------------------------------ a11y wiring --- */

test("the control is a real button wired to the panel it controls", () => {
  const renderer = render({ isOpen: true });
  const [button] = findAll(renderer, "button");

  assert.equal(button.props.type, "button", "an explicit type, so it never submits a form");
  assert.equal(button.props["aria-expanded"], true);

  const panelId = button.props["aria-controls"];
  assert.ok(panelId, "aria-controls must be set");

  const panel = renderer.root.findAll((node) => node.props?.id === panelId && node.type === "div");
  assert.equal(panel.length, 1, "aria-controls must resolve to exactly one panel");
  assert.equal(panel[0].props["aria-labelledby"], button.props.id, "the panel names its control back");
});

test("aria-expanded tracks the actual open state, in both directions", () => {
  assert.equal(findAll(render({ isOpen: false }), "button")[0].props["aria-expanded"], false);
  assert.equal(findAll(render({ isOpen: true }), "button")[0].props["aria-expanded"], true);
});

test("two rows on one page never share a panel id", () => {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(
      React.createElement(
        "div",
        null,
        React.createElement(RipMetricDisclosureRow, {
          key: "a",
          rowKey: "sameKey",
          title: "A",
          value: "1",
          metrics: METRICS,
          isOpen: true,
        }),
        React.createElement(RipMetricDisclosureRow, {
          key: "b",
          rowKey: "sameKey",
          title: "B",
          value: "2",
          metrics: METRICS,
          isOpen: true,
        })
      )
    );
  });

  const [first, second] = renderer.root.findAllByType("button");
  assert.notEqual(
    first.props["aria-controls"],
    second.props["aria-controls"],
    "even two rows with the same rowKey must control different panels"
  );
});

test("the control keeps focus-visible styling and is not nested in another control", () => {
  const renderer = render({ isOpen: false });
  const [button] = findAll(renderer, "button");
  assert.match(button.props.className, /focus-visible:ring-2/);

  // No button inside a button, and no button inside an anchor.
  const nested = renderer.root.findAll(
    (node) => (node.type === "button" || node.type === "a") && node.findAllByType("button").length > 1
  );
  assert.equal(nested.length, 0, "disclosure controls must never nest inside another control");
});

test("clicking the control reports the row's own key to the caller", () => {
  const seen = [];
  const renderer = render({ isOpen: false, onToggle: (key) => seen.push(key) });
  TestRenderer.act(() => {
    findAll(renderer, "button")[0].props.onClick();
  });
  assert.deepEqual(seen, ["trueWinFrequency"]);
});

/* ---------------------------------------------------------------- copy --- */

test("a disclaimer stays visible while the row is collapsed", () => {
  // The Desirable Outcome Frequency disclaimer changes how the visible number
  // must be read, so it can never be the thing behind the disclosure.
  const disclaimer = "A desirable outcome can still be worth less than the pack price.";
  const collapsed = textOf(render({ isOpen: false, disclaimer }).toJSON());
  const expanded = textOf(render({ isOpen: true, disclaimer }).toJSON());

  assert.ok(collapsed.includes(disclaimer), "visible without expanding");
  assert.ok(expanded.includes(disclaimer), "and still visible when expanded");
});

test("an unavailable value renders exactly what the selector supplied, never a zero", () => {
  const text = textOf(render({ value: "—", valueSuffix: null, metrics: [], isOpen: false }).toJSON());
  assert.ok(text.includes("—"));
  assert.ok(!/\b0\b/.test(text), "a missing value must never become a zero");
});

test("zero is a valid relative score, not an unavailable rail", () => {
  const renderer = render({ value: "0.0", railPercent: 0, metrics: [], isOpen: false });
  const rails = renderer.root.findAll(
    (node) => node.props?.["data-rip-metric-rail"] !== undefined
  );
  assert.equal(rails.length, 1);
  assert.equal(rails[0].props["data-rail-available"], "true");
  assert.equal(rails[0].children.length, 1, "zero has a real, zero-width fill rather than an unavailable state");
  assert.equal(rails[0].children[0].props.style.width, "0%");
  assert.ok(textOf(renderer.toJSON()).includes("0.0"));
});

test("the row renders no weight, contribution or formula", () => {
  const text = textOf(render({ isOpen: true }).toJSON());
  for (const banned of ["Weight", "weight", "Contributes", "contribution", "90%", "10%", "×", "="]) {
    assert.ok(!text.includes(banned), `"${banned}" must not appear on a metric row`);
  }
});

/* ------------------------------------------------------------- policy --- */

test("mobile keeps exactly one row open per section", () => {
  const mobile = { isDesktop: false };

  let open = resolveNextOpenKeys([], "a", mobile);
  assert.deepEqual(open, ["a"]);

  open = resolveNextOpenKeys(open, "b", mobile);
  assert.deepEqual(open, ["b"], "opening a new row closes the previous one");

  open = resolveNextOpenKeys(open, "c", mobile);
  assert.deepEqual(open, ["c"]);
});

test("desktop allows multiple rows open at once", () => {
  const desktop = { isDesktop: true };

  let open = resolveNextOpenKeys([], "a", desktop);
  open = resolveNextOpenKeys(open, "b", desktop);
  open = resolveNextOpenKeys(open, "c", desktop);

  assert.deepEqual(open, ["a", "b", "c"], "desktop accumulates rather than replacing");
});

test("closing an open row behaves identically at both widths", () => {
  for (const isDesktop of [true, false]) {
    const open = resolveNextOpenKeys(["a"], "a", { isDesktop });
    assert.deepEqual(open, [], `a closed row is closed (isDesktop=${isDesktop})`);
  }

  assert.deepEqual(
    resolveNextOpenKeys(["a", "b"], "a", { isDesktop: true }),
    ["b"],
    "closing one desktop row leaves the others open"
  );
});

test("the policy never mutates the set it was given", () => {
  const original = ["a"];
  resolveNextOpenKeys(original, "b", { isDesktop: true });
  resolveNextOpenKeys(original, "a", { isDesktop: true });
  assert.deepEqual(original, ["a"]);
});

test("two sections toggling independently cannot disturb each other", () => {
  // Each section owns its own array; the policy is a pure function of the one
  // it is handed, so there is no shared state for a cross-section leak.
  let financial = resolveNextOpenKeys([], "typicalRetention", { isDesktop: false });
  let collector = resolveNextOpenKeys([], "dualPathDepth", { isDesktop: false });

  collector = resolveNextOpenKeys(collector, "rosterDesirability", { isDesktop: false });

  assert.deepEqual(financial, ["typicalRetention"], "the Financial row stayed open");
  assert.deepEqual(collector, ["rosterDesirability"], "only the Collector section accordioned");
});
