import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import TestRenderer from "react-test-renderer";

import SealedProductPicker from "./SealedProductPicker.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// The picker moves REAL focus between option buttons and listens on document
// for dismissal, so it needs DOM-ish nodes. jsdom is not a dependency of this
// project, so react-test-renderer is driven with `createNodeMock` and a minimal
// document stub: enough of contains/querySelectorAll/focus/activeElement for
// the roving-focus and dismissal logic to run for real, rather than asserting
// on a reimplementation of it.

const PRODUCTS = [
  { sealedProductId: "pc-etb", productFamily: "pokemon_center_elite_trainer_box", name: "Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)", currentPrice: 422.6 },
  { sealedProductId: "etb", productFamily: "elite_trainer_box", name: "Ascended Heroes Elite Trainer Box", currentPrice: 169.41 },
  { sealedProductId: "bundle", productFamily: "booster_bundle", name: "Ascended Heroes Booster Bundle", currentPrice: 80.38 },
  { sealedProductId: "pack", productFamily: "booster_pack", name: "Ascended Heroes Booster Pack", currentPrice: 13.64 },
];

function createHarness() {
  const optionsByTitle = new Map();
  let order = [];
  let activeElement = null;
  let triggerNode = null;
  const listeners = new Map();

  const previousDocument = globalThis.document;
  globalThis.document = {
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    removeEventListener(type, handler) {
      listeners.set(type, (listeners.get(type) || []).filter((entry) => entry !== handler));
    },
    get activeElement() {
      return activeElement;
    },
  };

  // react-test-renderer only calls createNodeMock for host elements that carry
  // a ref, and the option buttons deliberately have none (focus reaches them
  // through the listbox's querySelectorAll, exactly as in the real DOM). So the
  // listbox mock owns the option nodes, keyed by title so each render returns
  // the same object identity.
  const optionNode = (title) => {
    if (!optionsByTitle.has(title)) {
      const node = { role: "option", title, disabled: false, focus() { activeElement = node; } };
      optionsByTitle.set(title, node);
    }
    return optionsByTitle.get(title);
  };

  const createNodeMock = (element) => {
    const { role } = element.props || {};
    if (role === "listbox") {
      return {
        querySelectorAll: () => order.map(optionNode),
        contains: (target) => target === "inside",
      };
    }
    if (element.props?.["aria-haspopup"] === "listbox") {
      triggerNode = { tagName: "BUTTON", focus() { activeElement = triggerNode; } };
      return triggerNode;
    }
    if (element.props?.["data-sealed-product-picker"] !== undefined) {
      return { contains: (target) => target === "inside" };
    }
    return null;
  };

  return {
    createNodeMock,
    setOrder(titles) { order = titles; },
    get activeElement() { return activeElement; },
    get trigger() { return triggerNode; },
    optionFor(title) { return optionNode(title); },
    fire(type, event) {
      for (const handler of [...(listeners.get(type) || [])]) handler(event);
    },
    restore() {
      if (previousDocument === undefined) delete globalThis.document;
      else globalThis.document = previousDocument;
    },
  };
}

async function renderPicker({ value = "pc-etb", products = PRODUCTS } = {}) {
  const harness = createHarness();
  harness.setOrder(products.map((item) => item.name));
  const changes = [];
  const openStates = [];
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      <SealedProductPicker
        products={products}
        value={value}
        onChange={(next) => changes.push(next)}
        onOpenChange={(next) => openStates.push(next)}
      />,
      { createNodeMock: harness.createNodeMock }
    );
  });

  const find = (predicate) => renderer.root.findAll(predicate, { deep: true });
  const trigger = () => find((node) => node.props?.["aria-haspopup"] === "listbox")[0];
  const listbox = () => find((node) => node.props?.role === "listbox")[0] || null;
  const options = () => find((node) => node.props?.role === "option");
  const open = async () => { await act(async () => { trigger().props.onClick(); }); };

  return { renderer, harness, changes, openStates, trigger, listbox, options, open, find };
}

function textOf(instance) {
  const parts = [];
  const walk = (node) => {
    if (typeof node === "string") parts.push(node);
    else if (Array.isArray(node)) node.forEach(walk);
    else if (node?.children) node.children.forEach(walk);
  };
  walk(instance.children);
  return parts.join("");
}

test("the trigger is a button with the listbox popup contract, not a native select", async () => {
  const { trigger, renderer, harness } = await renderPicker();
  assert.equal(trigger().type, "button");
  assert.equal(trigger().props.type, "button");
  assert.equal(trigger().props["aria-haspopup"], "listbox");
  assert.equal(trigger().props["aria-expanded"], false);
  assert.ok(trigger().props["aria-controls"], "trigger must point at the listbox id");

  // No native form control anywhere in the tree.
  assert.equal(renderer.root.findAll((node) => node.type === "select", { deep: true }).length, 0);
  assert.equal(renderer.root.findAll((node) => node.type === "option", { deep: true }).length, 0);
  harness.restore();
});

test("the trigger shows the concise label and keeps the full scraped name accessible", async () => {
  const { trigger, harness } = await renderPicker();
  // "PC ETB", not "PC ETB — Ascended Heroes Pokemon Center Elite Trainer Box".
  assert.equal(textOf(trigger()), "PC ETB");
  assert.doesNotMatch(textOf(trigger()), /Ascended Heroes/);
  assert.equal(trigger().props.title, "Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)");
  assert.match(trigger().props["aria-label"], /Ascended Heroes Pokemon Center Elite Trainer Box \(Exclusive\)/);
  harness.restore();
});

test("the menu is a listbox of options in the given price-descending order, each with its price", async () => {
  const { open, listbox, options, harness } = await renderPicker();
  assert.equal(listbox() === null, true, "menu is closed until opened");
  await open();

  assert.equal(listbox().props.role, "listbox");
  assert.equal(listbox().props["aria-label"], "Sealed products");
  assert.equal(options().length, 4);

  assert.deepEqual(options().map((row) => textOf(row)), [
    "PC ETB$422.60",
    "ETB$169.41",
    "Booster Bundle$80.38",
    "Booster Pack$13.64",
  ]);

  // Concise label only; the full name stays in title/aria-label.
  assert.doesNotMatch(textOf(options()[0]), /Ascended Heroes/);
  assert.equal(options()[0].props.title, "Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)");
  assert.match(options()[0].props["aria-label"], /Ascended Heroes Pokemon Center Elite Trainer Box \(Exclusive\), \$422\.60/);
  harness.restore();
});

test("the selected product is the only aria-selected option", async () => {
  const { open, options, trigger, harness } = await renderPicker({ value: "bundle" });
  assert.equal(textOf(trigger()), "Booster Bundle");
  await open();
  assert.deepEqual(options().map((row) => row.props["aria-selected"]), [false, false, true, false]);
  // No nested interactive element inside an option.
  assert.equal(options()[2].findAll((node) => node.type === "button", { deep: true }).length, 1);
  harness.restore();
});

test("choosing a product reports its id and closes the menu", async () => {
  const { open, options, listbox, trigger, changes, openStates, harness } = await renderPicker();
  await open();
  await act(async () => { options()[1].props.onClick(); });

  assert.deepEqual(changes, ["etb"]);
  assert.equal(listbox() === null, true, "selection closes the menu");
  assert.equal(trigger().props["aria-expanded"], false);
  assert.deepEqual(openStates, [true, false]);
  // Focus returns to the trigger rather than being dropped.
  assert.equal(harness.activeElement, harness.trigger);
  harness.restore();
});

test("opening moves focus to the current product and arrows rove with wraparound", async () => {
  const { open, listbox, harness } = await renderPicker({ value: "etb" });
  await open();
  // Focus lands on the selected row, not blindly on the first one.
  assert.equal(harness.activeElement.title, "Ascended Heroes Elite Trainer Box");

  const rows = [
    "Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)",
    "Ascended Heroes Elite Trainer Box",
    "Ascended Heroes Booster Bundle",
    "Ascended Heroes Booster Pack",
  ].map((title) => harness.optionFor(title));

  let prevented = 0;
  const press = async (key) => {
    await act(async () => {
      listbox().props.onKeyDown({
        key,
        preventDefault() { prevented += 1; },
        currentTarget: { querySelectorAll: () => rows },
      });
    });
  };

  await press("ArrowDown");
  assert.equal(harness.activeElement, rows[2]);
  await press("ArrowUp");
  assert.equal(harness.activeElement, rows[1]);
  await press("Home");
  assert.equal(harness.activeElement, rows[0]);
  await press("End");
  assert.equal(harness.activeElement, rows[3]);
  // Wraparound in both directions, matching the set picker's arithmetic.
  await press("ArrowDown");
  assert.equal(harness.activeElement, rows[0]);
  await press("ArrowUp");
  assert.equal(harness.activeElement, rows[3]);
  assert.equal(prevented, 6, "navigation keys must not also scroll the page");

  // Unrelated keys are left alone so typing and Tab still behave natively.
  await act(async () => {
    listbox().props.onKeyDown({ key: "a", preventDefault() { prevented += 1; }, currentTarget: { querySelectorAll: () => rows } });
  });
  assert.equal(prevented, 6);
  harness.restore();
});

test("ArrowDown and ArrowUp on the closed trigger open the menu at the first and last option", async () => {
  for (const [key, expected] of [["ArrowDown", 0], ["ArrowUp", 3]]) {
    const { trigger, listbox, harness } = await renderPicker();
    await act(async () => {
      trigger().props.onKeyDown({ key, preventDefault() {} });
    });
    assert.ok(listbox(), `${key} opens the menu`);
    const rows = [
      "Ascended Heroes Pokemon Center Elite Trainer Box (Exclusive)",
      "Ascended Heroes Elite Trainer Box",
      "Ascended Heroes Booster Bundle",
      "Ascended Heroes Booster Pack",
    ].map((title) => harness.optionFor(title));
    assert.equal(harness.activeElement, rows[expected]);
    harness.restore();
  }
});

test("Escape closes the menu and hands focus back to the trigger", async () => {
  const { open, listbox, harness } = await renderPicker();
  await open();
  assert.ok(listbox(), "menu is open");

  await act(async () => { harness.fire("keydown", { key: "Escape", stopPropagation() {} }); });
  assert.equal(listbox() === null, true);
  assert.equal(harness.activeElement, harness.trigger);
  harness.restore();
});

test("a pointer press outside closes the menu, one inside does not", async () => {
  const { open, listbox, harness } = await renderPicker();
  await open();

  await act(async () => { harness.fire("mousedown", { target: "inside" }); });
  assert.ok(listbox(), "a press inside the picker keeps it open");

  await act(async () => { harness.fire("mousedown", { target: "outside" }); });
  assert.equal(listbox() === null, true, "a press outside closes it");
  harness.restore();
});

test("an empty product list disables the trigger instead of opening an empty menu", async () => {
  const { trigger, listbox, open, openStates, harness } = await renderPicker({ products: [], value: null });
  assert.equal(trigger().props.disabled, true);
  await open();
  // No stray frosted rectangle over the chart, and the card is never told to
  // raise itself for a menu that does not exist.
  assert.equal(listbox() === null, true);
  assert.equal(trigger().props["aria-expanded"], false);
  assert.deepEqual(openStates, [false]);
  harness.restore();
});
