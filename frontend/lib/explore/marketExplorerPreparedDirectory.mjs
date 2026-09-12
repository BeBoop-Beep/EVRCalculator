export const PREPARED_DIRECTORY_STATUS = Object.freeze({
  ready: "ready",
  empty: "empty",
  unavailable: "unavailable",
});

export function preparedDirectoryResult(markets) {
  if (!Array.isArray(markets)) return unavailablePreparedDirectory({ errorCode: "PREPARED_DIRECTORY_INVALID_PAYLOAD", httpStatus: 200 });
  const rows = markets;
  return {
    status: rows.length ? PREPARED_DIRECTORY_STATUS.ready : PREPARED_DIRECTORY_STATUS.empty,
    markets: rows,
    errorCode: null,
    httpStatus: 200,
  };
}

export function unavailablePreparedDirectory({ errorCode = "PREPARED_DIRECTORY_UNAVAILABLE", httpStatus = null } = {}) {
  return {
    status: PREPARED_DIRECTORY_STATUS.unavailable,
    markets: [],
    errorCode,
    httpStatus,
  };
}
