"use client";
import { createContext, useState, useEffect, useContext, useCallback } from "react";
import { useRouter } from "next/navigation";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // Track the user state
  const router = useRouter();

  // Re-usable auth fetch: resolves the current session from the httpOnly token cookie.
  // Called on mount and explicitly after login to hydrate state without a full page reload.
  const refreshUser = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/me", {
        method: "GET",
        credentials: "include",
      });

      if (!response.ok) {
        setUser(null);
        return;
      }

      const data = await response.json();
      setUser(data.user || null);
    } catch (error) {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

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
  
      if (response.ok && data.token) {
        const meResponse = await fetch("/api/auth/me", {
          method: "GET",
          credentials: "include",
        });

        if (meResponse.ok) {
          const meData = await meResponse.json();
          setUser(meData.user || { token: data.token });
        } else {
          setUser({ token: data.token });
        }

        return { token: data.token };
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
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
