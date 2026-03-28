"use client";
import { createContext, useState, useEffect, useContext } from "react";
import { useRouter } from "next/navigation";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // Track the user state
  const router = useRouter();

  useEffect(() => {
    const token = document.cookie
      .split("; ")
      .find((row) => row.startsWith("token="));
    if (token) {
      setUser({ token: token.split("=")[1] });
    }
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
  
      if (data.token) {
        document.cookie = `token=${data.token}; path=/; max-age=${60 * 60 * 24}; SameSite=Strict`;
        setUser({ token: data.token });
        return { token: data.token };
      } else {
        return { error: data.message || "Invalid credentials" };
      }
    } catch (error) {
      console.error("Login error:", error);
      return { error: "Login failed. Please try again." };
    }
  };
  

  const logout = () => {
    // Clear the cookie and update state
    document.cookie = "token=; path=/; max-age=0; Secure; SameSite=Strict";

    setUser(null); // Reset user state
    router.push("/login"); // Redirect to login page
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
