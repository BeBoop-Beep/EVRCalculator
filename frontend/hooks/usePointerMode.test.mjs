import test from "node:test";
import assert from "node:assert/strict";

import {
  POINTER_MODE_COARSE,
  POINTER_MODE_FINE,
  resolvePointerModeFromEvent,
} from "./pointerMode.mjs";

test("touch and pen switch the page into tap mode", () => {
  assert.equal(resolvePointerModeFromEvent({ pointerType: "touch" }, POINTER_MODE_FINE), POINTER_MODE_COARSE);
  assert.equal(resolvePointerModeFromEvent({ pointerType: "pen" }, POINTER_MODE_FINE), POINTER_MODE_COARSE);
});

test("a mouse switches back to hover mode on the same device", () => {
  // Hybrid laptops and tablets with a trackpad must keep both modes. Whichever
  // device was used last wins; neither is permanently disabled.
  assert.equal(resolvePointerModeFromEvent({ pointerType: "mouse" }, POINTER_MODE_COARSE), POINTER_MODE_FINE);
});

test("unknown or missing pointer types leave the mode alone", () => {
  assert.equal(resolvePointerModeFromEvent({ pointerType: "" }, POINTER_MODE_COARSE), POINTER_MODE_COARSE);
  assert.equal(resolvePointerModeFromEvent({}, POINTER_MODE_FINE), POINTER_MODE_FINE);
  assert.equal(resolvePointerModeFromEvent(null, POINTER_MODE_FINE), POINTER_MODE_FINE);
});

test("a full hybrid sequence never gets stuck in one mode", () => {
  // touch -> mouse -> touch, the exact sequence a touchscreen laptop produces.
  let mode = POINTER_MODE_FINE;
  mode = resolvePointerModeFromEvent({ pointerType: "touch" }, mode);
  assert.equal(mode, POINTER_MODE_COARSE);
  mode = resolvePointerModeFromEvent({ pointerType: "mouse" }, mode);
  assert.equal(mode, POINTER_MODE_FINE);
  mode = resolvePointerModeFromEvent({ pointerType: "touch" }, mode);
  assert.equal(mode, POINTER_MODE_COARSE);
});

test("the first deliberate touch is not consumed switching modes", () => {
  // The regression this guards: if the hook only learned "coarse" from the
  // first pointerdown, that first tap would flip the mode and the tooltip would
  // need a second tap. The capability seed must already have resolved coarse
  // before any user input, and a touch pointerdown must not change the mode
  // that a coarse-seeded device is already in.
  const seeded = POINTER_MODE_COARSE; // what the matchMedia seed produces on a phone
  assert.equal(
    resolvePointerModeFromEvent({ pointerType: "touch" }, seeded),
    seeded,
    "the first touch leaves an already-coarse device alone, so the tap does its real job"
  );
});
