export const AUTH_RESOLUTION = Object.freeze({
  AUTHENTICATED: "authenticated",
  UNAUTHENTICATED: "unauthenticated",
  TRANSIENT_FAILURE: "transient_failure",
});

export async function resolveCurrentUser({ signal, fetchImpl = globalThis.fetch } = {}) {
  try {
    const response = await fetchImpl("/api/auth/me", {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal,
    });

    if (response.status === 401 || response.status === 403) {
      return { kind: AUTH_RESOLUTION.UNAUTHENTICATED, user: null, status: response.status };
    }

    if (!response.ok) {
      return { kind: AUTH_RESOLUTION.TRANSIENT_FAILURE, status: response.status };
    }

    const payload = await response.json();
    if (!payload?.user || typeof payload.user !== "object") {
      return { kind: AUTH_RESOLUTION.TRANSIENT_FAILURE, status: response.status };
    }

    return { kind: AUTH_RESOLUTION.AUTHENTICATED, user: payload.user, status: response.status };
  } catch (error) {
    return {
      kind: AUTH_RESOLUTION.TRANSIENT_FAILURE,
      aborted: error?.name === "AbortError",
      error,
    };
  }
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

export function canonicalUsersEqual(left, right) {
  if (left === right) return true;
  if (!left || !right) return false;
  return JSON.stringify(stableValue(left)) === JSON.stringify(stableValue(right));
}

export function reconcileAuthResult(currentUser, result) {
  if (result.kind === AUTH_RESOLUTION.AUTHENTICATED) {
    return { user: result.user, changed: !canonicalUsersEqual(currentUser, result.user), degraded: false };
  }
  if (result.kind === AUTH_RESOLUTION.UNAUTHENTICATED) {
    return { user: null, changed: currentUser !== null, degraded: false };
  }
  return { user: currentUser, changed: false, degraded: true };
}

export function createAuthRequestCoordinator() {
  let generation = 0;
  let active = null;

  return {
    begin(mode) {
      if (mode === "soft" && active?.mode === "strong") return null;
      active?.controller.abort();
      const token = { mode, generation: ++generation, controller: new AbortController() };
      active = token;
      return token;
    },
    isCurrent(token) {
      return active === token && token.generation === generation;
    },
    finish(token) {
      if (active === token) active = null;
    },
    cancel() {
      generation += 1;
      active?.controller.abort();
      active = null;
    },
  };
}
