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

export default classNames;
