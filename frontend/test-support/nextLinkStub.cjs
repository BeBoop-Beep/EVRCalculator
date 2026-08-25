// A renderable stand-in for `next/link`.
//
// Next's Link reads the App Router context on render and throws outside a real
// Next tree, so any component that links to another page is unrenderable under
// `tsx --test` even though it renders correctly in the app.
//
// The stub produces the thing Link actually produces — an anchor carrying the
// href — which is exactly what a test asserting "this row links to
// /Market/Explorer?market=raw" needs to see. Next-only props are dropped rather
// than leaked onto the DOM element as unknown attributes.
const React = require("react");

const NextLinkStub = React.forwardRef(function NextLinkStub(props, ref) {
  const { href, children, prefetch, replace, scroll, shallow, locale, legacyBehavior, ...rest } = props;
  const url = typeof href === "string" ? href : href?.pathname || "";
  return React.createElement("a", { ...rest, ref, href: url }, children);
});

module.exports = NextLinkStub;
module.exports.default = NextLinkStub;
module.exports.__esModule = true;
