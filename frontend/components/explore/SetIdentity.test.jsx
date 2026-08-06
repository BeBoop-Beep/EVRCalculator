// SetIdentity renders identity and nothing else.
//
// This is a BEHAVIOURAL test, not a source-string one: the component is now
// dependency-free (no "@/" aliases, no CSS module), so it can be rendered
// directly and the rendered tree inspected for the retired interpretation
// verdict. The point is not that the source lacks a variable name — it is that
// no interpretation copy reaches the DOM even when every retired field is
// present and populated on the target.

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

import SetIdentity from "./SetIdentity.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Every output of the retired Profit/Safety/Stability interpretation engine,
// on the target AND as props the old component accepted, with values distinct
// enough that any leak into the tree is unmistakable.
const INTERPRETATION_TEXT = [
  "Elite but swingy",
  "STRONG VALUE PROFILE",
  "Strong value, high variance",
];

const LOUD_TARGET = {
  name: "Chaos Rising",
  era: "Scarlet & Violet",
  logo_image_url: "https://images.example/logo.png",
  leaderboard_label: "STRONG VALUE PROFILE",
  canonical_recommendation_header: "Strong value, high variance",
  recommendation_severity: "positive",
  interpretationLabel: "Elite but swingy",
  interpretationSummary: "A verdict from a retired model.",
};

function renderIdentity(props) {
  let renderer;
  TestRenderer.act(() => {
    renderer = TestRenderer.create(React.createElement(SetIdentity, props));
  });
  return renderer;
}

function textOf(renderer) {
  const collected = [];
  const walk = (node) => {
    if (node === null || node === undefined || node === false) return;
    if (typeof node === "string" || typeof node === "number") {
      collected.push(String(node));
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    walk(node.children);
  };
  walk(renderer.toJSON());
  return collected.join(" ");
}

for (const variant of ["compact", "default"]) {
  test(`SetIdentity (${variant}) renders no interpretation verdict`, () => {
    const renderer = renderIdentity({
      variant,
      target: LOUD_TARGET,
      // The props the old component took. They are no longer part of the
      // signature; passing them proves a caller that has not been updated
      // still cannot put a verdict on screen.
      interpretationLabel: "Elite but swingy",
      recommendationSeverity: "positive",
      tier: "S",
    });

    const text = textOf(renderer);
    assert.ok(text.includes("Chaos Rising"), "identity must survive");
    assert.ok(text.includes("Scarlet & Violet"), "era must survive");

    for (const phrase of INTERPRETATION_TEXT) {
      assert.ok(!text.includes(phrase), `"${phrase}" must not render in the ${variant} variant`);
    }
  });
}

test("SetIdentity output is identical with and without interpretation fields", () => {
  const bare = {
    name: LOUD_TARGET.name,
    era: LOUD_TARGET.era,
    logo_image_url: LOUD_TARGET.logo_image_url,
  };

  // Serialised so the comparison is over markup and props, not over the
  // identity of the per-render `onError` closure, which differs between any two
  // renders and says nothing about interpretation copy.
  const shape = (renderer) =>
    JSON.stringify(renderer.toJSON(), (_key, value) =>
      typeof value === "function" ? "[fn]" : value
    );

  for (const variant of ["compact", "default"]) {
    assert.equal(
      shape(renderIdentity({ variant, target: LOUD_TARGET })),
      shape(renderIdentity({ variant, target: bare })),
      `interpretation fields must be completely inert in the ${variant} variant`
    );
  }
});

test("a set with no era still renders its name without a dangling separator", () => {
  const renderer = renderIdentity({ variant: "compact", target: { name: "No Era Set" } });
  const text = textOf(renderer);

  assert.ok(text.includes("No Era Set"));
  assert.ok(!text.includes("·"), "the era/verdict separator must not survive alone");
});
