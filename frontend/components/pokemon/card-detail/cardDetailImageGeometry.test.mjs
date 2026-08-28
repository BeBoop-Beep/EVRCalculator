import assert from "node:assert/strict";
import test from "node:test";
import { getObjectContainPaintedRect } from "./cardDetailImageGeometry.mjs";

test("matching aspect ratios fill the element box", () => {
  assert.deepEqual(
    getObjectContainPaintedRect({
      imageRect: { left: 10, top: 20, width: 200, height: 300 },
      naturalWidth: 400,
      naturalHeight: 600,
    }),
    { left: 10, top: 20, width: 200, height: 300 },
  );
});

test("horizontal letterboxing centers painted content", () => {
  assert.deepEqual(
    getObjectContainPaintedRect({
      imageRect: { left: 0, top: 5, width: 300, height: 300 },
      naturalWidth: 100,
      naturalHeight: 200,
    }),
    { left: 75, top: 5, width: 150, height: 300 },
  );
});

test("vertical letterboxing centers painted content", () => {
  assert.deepEqual(
    getObjectContainPaintedRect({
      imageRect: { left: 5, top: 10, width: 300, height: 300 },
      naturalWidth: 200,
      naturalHeight: 100,
    }),
    { left: 5, top: 85, width: 300, height: 150 },
  );
});

test("arbitrary natural dimensions preserve their aspect ratio", () => {
  const result = getObjectContainPaintedRect({
    imageRect: { left: 12, top: 18, width: 420, height: 500 },
    naturalWidth: 734,
    naturalHeight: 1024,
  });
  assert.ok(Math.abs(result.width / result.height - 734 / 1024) < 1e-12);
  assert.ok(Math.abs(result.left - (12 + (420 - result.width) / 2)) < 1e-12);
});

test("invalid and zero dimensions fail closed", () => {
  assert.equal(
    getObjectContainPaintedRect({
      imageRect: { left: 0, top: 0, width: 0, height: 10 },
      naturalWidth: 10,
      naturalHeight: 10,
    }),
    null,
  );
  assert.equal(
    getObjectContainPaintedRect({
      imageRect: { left: 0, top: 0, width: 10, height: 10 },
      naturalWidth: 0,
      naturalHeight: 10,
    }),
    null,
  );
  assert.equal(getObjectContainPaintedRect(), null);
});
