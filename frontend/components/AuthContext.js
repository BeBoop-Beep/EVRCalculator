"use client";
import { createContext, useState, useEffect, useContext, useCallback, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  AUTH_RESOLUTION,
  canonicalUsersEqual,
  createAuthRequestCoordinator,
  reconcileAuthResult,
  resolveCurrentUser,
} from "@/lib/auth/clientAuthLifecycle.mjs";

const AuthContext = createContext();

export function AuthProvider({ children, initialUser = null }) {
  const [user, setUser] = useState(initialUser); // Track the user state
  const [authStatus, setAuthStatus] = useState("resolved");
  const [authRevision, setAuthRevision] = useState(0);
  const router = useRouter();
  const pathname = usePathname();
  const userRef = useRef(initialUser);
  const previousPathnameRef = useRef(null);
  const requestCoordinatorRef = useRef(null);
  if (requestCoordinatorRef.current === null) {
    requestCoordinatorRef.current = createAuthRequestCoordinator();
  }

  const commitUser = useCallback((nextUser) => {
    if (canonicalUsersEqual(userRef.current, nextUser)) return false;
    userRef.current = nextUser;
    setUser(nextUser);
    setAuthRevision((value) => value + 1);
    return true;
  }, []);

  const runAuthResolution = useCallback(async (mode) => {
    // An explicit refresh represents a real auth/profile mutation. A background
    // route sync must never cancel or supersede it.
    const request = requestCoordinatorRef.current.begin(mode);
    if (!request) return userRef.current;
    setAuthStatus("resolving");

    const result = await resolveCurrentUser({ signal: request.controller.signal });
    if (!requestCoordinatorRef.current.isCurrent(request)) return userRef.current;

    const reconciliation = reconcileAuthResult(userRef.current, result);
    if (reconciliation.changed) commitUser(reconciliation.user);
    setAuthStatus(reconciliation.degraded ? "degraded" : "resolved");
    requestCoordinatorRef.current.finish(request);
    return result.kind === AUTH_RESOLUTION.AUTHENTICATED ? result.user : reconciliation.user;
  }, [commitUser]);

  // Routine route/focus reconciliation is deliberately client-only: it keeps
  // the persistent shell canonical without rebuilding Server Components.
  const syncUser = useCallback(() => runAuthResolution("soft"), [runAuthResolution]);

  const refreshUser = useCallback(async () => {
    const nextUser = await runAuthResolution("strong");
    // Explicit mutation callers need entitlement-aware Server Components to
    // resolve the same cookie-backed identity. Soft navigation sync never does this.
    router.refresh();
    return nextUser;
  }, [router, runAuthResolution]);

  useEffect(() => {
    commitUser(initialUser);

    if (!initialUser) {
      return;
    }

    console.info("[AuthContext] hydration_auth_reuse", {
      authResolution: "reused_server_state",
      hasInitialUser: Boolean(initialUser?.id),
    });
  }, [commitUser, initialUser]);

  useEffect(() => {
    const previousPathname = previousPathnameRef.current;
    previousPathnameRef.current = pathname;

    // The server seed owns first paint. Only a missing seed needs a mount-time
    // check (for example, an OAuth/client transition that just set the cookie).
    if (previousPathname === null) {
      if (!initialUser) void syncUser();
      return;
    }
    if (previousPathname !== pathname) void syncUser();
  }, [initialUser, pathname, syncUser]);

  useEffect(() => () => {
    requestCoordinatorRef.current.cancel();
  }, []);

  const login = async (email, password) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });
  
      const data = await response.json();
  
      if (response.ok) {
        await refreshUser();
        return { success: true };
      } else {
        return { error: data.message || "Invalid credentials" };
      }
    } catch (error) {
      console.error("Login error:", error);
      return { error: "Login failed. Please try again." };
    }
  };
  

  const logout = async () => {
    try {
      await fetch("/api/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch (error) {
      // Even if API logout fails, clear local auth state.
    }

    requestCoordinatorRef.current.cancel();
    commitUser(null);
    setAuthStatus("resolved");
    router.refresh();
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshUser, syncUser, authStatus, authRevision }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
