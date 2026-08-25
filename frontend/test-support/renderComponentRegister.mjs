// Make CSS Modules importable under `tsx --test`.
//
// Next.js resolves `*.module.css` to an object of generated class names. Node
// has no such loader, so any component that imports one is unrenderable in a
// test until this hook exists — which is why the repo's component tests have so
// far been limited to reading source text.
//
// The stub returns the requested key as its own class name. That is enough for
// rendering, and it makes `styles.breakEvenEntertainment` assertable in a test
// as the literal string "breakEvenEntertainment".
//
// IMPORT THIS FIRST. ES module dependencies are evaluated in import order, so
// the hook must be registered by an import that precedes the component's.

import Module from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";

// THE CLASSIC JSX RUNTIME NEEDS `React` IN SCOPE.
//
// Next.js compiles JSX with the automatic runtime, so application components
// correctly do not import React. The repo's `tsx --test` runner compiles them
// with the CLASSIC runtime instead, which emits `React.createElement(...)` and
// then throws "React is not defined" at render time — for the component under
// test AND for every component it renders, so importing React in one file does
// not fix it.
//
// Publishing React globally satisfies the classic runtime's scope lookup for
// the whole tree without adding a tooling-driven import to application source.
globalThis.React = globalThis.React || React;

const classNames = new Proxy(
  {},
  {
    get(_target, key) {
      // Leave the CommonJS/ESM interop markers alone: claiming to be an ES
      // module, or answering to `default` with a string, would make the
      // importing component receive a string instead of the class map.
      if (typeof key !== "string") return undefined;
      if (key === "__esModule" || key === "default") return undefined;
      return key;
    },
  },
);

Module._extensions[".css"] = function stubCssModule(module) {
  module.exports = classNames;
};

// THE `@/` ALIAS, RESOLVED LOCALLY RATHER THAN GLOBALLY.
//
// Application components import siblings as `@/components/...`, which Next.js
// resolves from `jsconfig.json`. `tsx` reads only `tsconfig.json`, so the alias
// is unresolvable under the test runner and any component using one crashes on
// import.
//
// The obvious fix — pointing the runner at `jsconfig.json` via the shared
// `test:frontend` script — is a GLOBAL change: it also un-crashes unrelated
// test files that have been failing silently behind that same import error,
// which has nothing to do with this feature and turns one crash into a spread
// of newly visible failures in an unrelated review.
//
// So the alias is resolved HERE instead, in a module that only the tests which
// actually render a component import. Scope of effect: this process, after this
// import. The shared runner script stays untouched.
const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
// `next/link` IS UNRENDERABLE UNDER THIS RUNNER.
//
// Next's Link reads the App Router context on render and throws outside a real
// Next tree, so a component that links to another page cannot be rendered here
// at all — the whole subtree fails, not just the link. It is redirected to a
// local stub that renders the anchor Link actually produces, so a test can
// assert where a row navigates to. Scope of effect is the same as the alias
// below: this process, after this import.
const nextLinkStub = path.join(frontendRoot, "test-support", "nextLinkStub.cjs");

const resolveFilename = Module._resolveFilename;
Module._resolveFilename = function resolveWithAlias(request, ...rest) {
  if (request === "next/link") return nextLinkStub;
  const aliased = request.startsWith("@/")
    ? path.join(frontendRoot, request.slice(2))
    : request;
  return resolveFilename.call(this, aliased, ...rest);
};

export default classNames;
