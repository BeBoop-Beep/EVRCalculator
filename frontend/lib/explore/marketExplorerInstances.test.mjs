import test from "node:test";
import assert from "node:assert/strict";
import { attachMarketInstance, exactBasketLabel, replaceMarketInstance, specsAreEquivalent } from "./marketExplorerInstances.mjs";

const spec = (ids) => ({ asset: "cards", membershipMode: "explicit", instrumentIds: ids });
const result = (ids, fingerprint = "fp") => ({ key: `query:${fingerprint}`, queryFingerprint: fingerprint, asset: "cards", color: "#123", softColor: "#234", spec: spec(ids), trend: [] });

test("instance identity is separate from the semantic fingerprint", () => {
  const instance = attachMarketInstance(result(["a"]), { exactItems: [{ instrumentId: "a", name: "Charizard" }] });
  assert.notEqual(instance.instanceId, instance.queryFingerprint);
  assert.equal(instance.key, instance.instanceId);
});

test("an update retains instance identity and visual identity while fingerprint changes", () => {
  const before = attachMarketInstance(result(["a"]));
  const after = replaceMarketInstance(before, result(["a", "b"], "next"));
  assert.equal(after.instanceId, before.instanceId);
  assert.equal(after.key, before.key);
  assert.equal(after.color, before.color);
  assert.equal(after.queryFingerprint, "next");
});

test("canonical spec comparison ignores explicit item order", () => {
  assert.equal(specsAreEquivalent(spec(["b", "a"]), spec(["a", "b"])), true);
});

test("exact basket labels are human and do not affect semantic identity", () => {
  assert.equal(exactBasketLabel([{ name: "Charizard" }, { name: "Blastoise" }]), "Charizard + Blastoise");
  assert.equal(exactBasketLabel([{ name: "A" }, { name: "B" }, { name: "C" }]), "3-Card Custom Basket");
});
