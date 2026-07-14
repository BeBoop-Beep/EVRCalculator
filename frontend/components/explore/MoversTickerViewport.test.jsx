import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import MoversTickerViewport from "./MoversTickerViewport.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const destination = "/sets/chaos-rising?tab=cards&section=market-movers&card_sort=7d-movers&movement=all";

function sequence(ariaHidden, ref) {
  return (
    <div
      ref={ref}
      aria-hidden={ariaHidden ? "true" : undefined}
      className={ariaHidden ? "index-ticker-duplicate" : "index-ticker-original"}
    >
      <a href={destination} tabIndex={ariaHidden ? -1 : undefined}>
        Mover
      </a>
    </div>
  );
}

async function renderViewport({ sequenceWidth = 600, reducedMotion = false } = {}) {
  const previousWindow = globalThis.window;
  const previousResizeObserver = globalThis.ResizeObserver;
  globalThis.window = {
    matchMedia: () => ({
      matches: reducedMotion,
      addEventListener() {},
      removeEventListener() {},
    }),
  };
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    disconnect() {}
  };

  const viewportNode = { clientWidth: 200, contains: () => false };
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <MoversTickerViewport
        hasItems
        items={[{ id: "mover" }]}
        renderSequence={sequence}
        fallback={<span>Empty</span>}
      />,
      {
        createNodeMock(element) {
          if (element.props.className?.includes("index-ticker-viewport")) return viewportNode;
          if (element.props.className === "index-ticker-original") return { scrollWidth: sequenceWidth };
          return {};
        },
      }
    );
  });

  return {
    renderer,
    async restore() {
      await act(async () => renderer.unmount());
      globalThis.window = previousWindow;
      globalThis.ResizeObserver = previousResizeObserver;
    },
  };
}

function findTrack(root) {
  return root.find((node) => node.props.className?.split(" ").includes("index-ticker-track"));
}

test("pointer or keyboard focus pauses without removing the track or duplicate link", async (context) => {
  const fixture = await renderViewport();
  context.after(() => fixture.restore());
  const { root } = fixture.renderer;
  const viewport = root.findByProps({ "aria-label": "7-day market movers" });
  const trackBefore = findTrack(root);
  const duplicateBefore = root.findByProps({ className: "index-ticker-duplicate" });
  const duplicateLinkBefore = duplicateBefore.findByType("a");

  await act(async () => viewport.props.onFocusCapture());

  const trackAfter = findTrack(root);
  const duplicateAfter = root.findByProps({ className: "index-ticker-duplicate" });
  const duplicateLinkAfter = duplicateAfter.findByType("a");
  assert.strictEqual(trackAfter, trackBefore);
  assert.strictEqual(duplicateAfter, duplicateBefore);
  assert.strictEqual(duplicateLinkAfter, duplicateLinkBefore);
  assert.equal(trackAfter.props.style.animationPlayState, "paused");
});

test("blur resumes the existing track instead of resetting or remounting it", async (context) => {
  const fixture = await renderViewport();
  context.after(() => fixture.restore());
  const { root } = fixture.renderer;
  const viewport = root.findByProps({ "aria-label": "7-day market movers" });
  const trackBefore = findTrack(root);
  const duplicateBefore = root.findByProps({ className: "index-ticker-duplicate" });

  await act(async () => viewport.props.onFocusCapture());
  await act(async () => viewport.props.onBlurCapture({ relatedTarget: null }));

  assert.strictEqual(findTrack(root), trackBefore);
  assert.strictEqual(root.findByProps({ className: "index-ticker-duplicate" }), duplicateBefore);
  assert.equal(findTrack(root).props.style.animationPlayState, undefined);
});

test("both copies expose the real destination and ordinary or modified clicks are not intercepted", async (context) => {
  const fixture = await renderViewport();
  context.after(() => fixture.restore());
  const links = fixture.renderer.root.findAllByType("a");

  assert.equal(links.length, 2);
  for (const link of links) {
    assert.equal(link.props.href, destination);
    assert.equal(link.props.onClick, undefined);
    for (const click of [{ button: 0 }, { button: 0, ctrlKey: true }, { button: 0, metaKey: true }, { button: 1 }]) {
      let defaultPrevented = false;
      link.props.onClick?.({ ...click, preventDefault: () => (defaultPrevented = true) });
      assert.equal(defaultPrevented, false);
    }
  }
  assert.equal(links[0].props.tabIndex, undefined);
  assert.equal(links[1].props.tabIndex, -1);
});

test("hover uses animation-play-state and has no component event that can remount the track", async (context) => {
  const fixture = await renderViewport();
  context.after(() => fixture.restore());
  const viewport = fixture.renderer.root.findByProps({ "aria-label": "7-day market movers" });
  const track = findTrack(fixture.renderer.root);
  const css = fs.readFileSync(path.resolve("app/styles/globals.css"), "utf8").replace(/\r\n/g, "\n");

  assert.match(
    css,
    /\.index-ticker-viewport:hover \.index-ticker-track,\n\.index-ticker-viewport:focus-within \.index-ticker-track \{\n  animation-play-state: paused;/
  );
  assert.equal(viewport.props.onMouseEnter, undefined);
  assert.equal(viewport.props.onMouseLeave, undefined);
  assert.strictEqual(findTrack(fixture.renderer.root), track);
  assert.equal(track.props.style.transform, undefined);
});

test("reduced motion and non-overflow presentations stay static and omit the duplicate", async (context) => {
  const reduced = await renderViewport({ reducedMotion: true });
  const fitting = await renderViewport({ sequenceWidth: 100 });
  context.after(async () => {
    await fitting.restore();
    await reduced.restore();
  });

  for (const fixture of [reduced, fitting]) {
    assert.equal(fixture.renderer.root.findAllByProps({ className: "index-ticker-duplicate" }).length, 0);
    assert.equal(fixture.renderer.root.findAll((node) => node.props.className?.includes("index-ticker-track")).length, 0);
    assert.equal(fixture.renderer.root.findAllByType("a").length, 1);
  }
});
