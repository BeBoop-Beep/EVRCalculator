// Pure pointer-mode logic, kept in .mjs so the node:test suite can import it
// directly. `frontend/package.json` has no "type": "module", so a .js file is
// CommonJS to node's ESM loader and an .mjs test cannot read its named exports.
// This mirrors moversTickerSelector.mjs and the rest of the explore selectors.

export const POINTER_MODE_FINE = "fine";
export const POINTER_MODE_COARSE = "coarse";

// Viewport width does not determine input type: a tablet may be driven by
// touch, a mouse or a trackpad, and a laptop may have a touchscreen. Resolve
// the mode from the pointer that was actually used most recently, seeded from
// the device's own capability query.
export function resolvePointerModeFromEvent(event, currentMode) {
  const pointerType = event?.pointerType;
  if (pointerType === "touch" || pointerType === "pen") {
    return POINTER_MODE_COARSE;
  }
  if (pointerType === "mouse") {
    return POINTER_MODE_FINE;
  }
  return currentMode;
}
