"use client";
import { createContext, useState, useEffect, useContext, useCallback } from "react";
import { useRouter } from "next/navigation";

const AuthContext = createContext();

export function AuthProvider({ children, initialUser = null }) {
  const [user, setUser] = useState(initialUser); // Track the user state
  const [authStatus, setAuthStatus] = useState("resolved");
  const [authRevision, setAuthRevision] = useState(0);
  const router = useRouter();

  // Re-usable auth fetch: resolves the current session from the httpOnly token cookie.
  // Called on mount and explicitly after login to hydrate state without a full page reload.
  const refreshUser = useCallback(async () => {
    setAuthStatus("resolving");
    try {
      const response = await fetch("/api/auth/me", {
        method: "GET",
        credentials: "include",
      });

      if (!response.ok) {
        setUser(null);
        setAuthRevision((value) => value + 1);
        router.refresh();
        return null;
      }

      const data = await response.json();
      const nextUser = data.user || null;
      setUser(nextUser);
      setAuthRevision((value) => value + 1);
      // Rebuild entitlement-aware Server Components from the canonical
      // httpOnly-cookie session. This preserves the current URL and client
      // state where Next can reconcile it; it never client-unlocks paid data.
      router.refresh();
      return nextUser;
    } catch (error) {
      setUser(null);
      setAuthRevision((value) => value + 1);
      router.refresh();
      return null;
    } finally {
      setAuthStatus("resolved");
    }
  }, [router]);

  useEffect(() => {
    setUser(initialUser);

    if (!initialUser) {
      return;
    }

    console.info("[AuthContext] hydration_auth_reuse", {
      authResolution: "reused_server_state",
      hasInitialUser: Boolean(initialUser?.id),
    });
  }, [initialUser]);

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

    setUser(null);
    setAuthRevision((value) => value + 1);
    router.refresh();
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshUser, authStatus, authRevision }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
