import test from "node:test";
import assert from "node:assert/strict";
import { PREPARED_DIRECTORY_STATUS, preparedDirectoryResult, unavailablePreparedDirectory } from "./marketExplorerPreparedDirectory.mjs";

test("successful prepared authority distinguishes ready from canonical empty", () => {
  assert.equal(preparedDirectoryResult([{ market_key: "set:one" }]).status, PREPARED_DIRECTORY_STATUS.ready);
  assert.equal(preparedDirectoryResult([]).status, PREPARED_DIRECTORY_STATUS.empty);
});

test("prepared authority failure is never represented as an empty directory", () => {
  const result = unavailablePreparedDirectory({ errorCode: "PREPARED_DIRECTORY_FAILED", httpStatus: 503 });
  assert.equal(result.status, PREPARED_DIRECTORY_STATUS.unavailable);
  assert.equal(result.httpStatus, 503);
  assert.equal(result.errorCode, "PREPARED_DIRECTORY_FAILED");
  assert.deepEqual(result.markets, []);
  assert.equal(preparedDirectoryResult(null).status, PREPARED_DIRECTORY_STATUS.unavailable);
  assert.equal(preparedDirectoryResult({}).errorCode, "PREPARED_DIRECTORY_INVALID_PAYLOAD");
});
