"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const router = useRouter();

  const handleLogin = async () => {
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
        credentials: "include", // Ensure cookies are sent and received automatically
      });

      if (response.ok) {
        // Since token is handled by the server (set in cookies), no need to store it on frontend
        router.push("/dashboard"); // Redirect to dashboard after login
      } else {
        const errorData = await response.json();
        setError(errorData?.message || "Invalid credentials.");
      }
    } catch (error) {
      console.error("Login error:", error); // Log the actual error for debugging
      setError("An error occurred while logging in.");
    }
  };

  const handleLogout = async () => {
    try {
      const response = await fetch("/api/logout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include", // Ensure cookies are sent and received automatically
      });

      if (response.ok) {
        router.push("/login"); // Redirect to login page after logout
      } else {
        setError("Logout failed");
      }
    } catch (error) {
      console.error("Logout error:", error);
      setError("An error occurred during logout.");
    }
  };

  return (
    <div className="container mx-auto p-6 py-16">
      <div>
        <h2 className="text-4xl font-bold text-center text-primary mb-6">
          Login
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault(); // Prevent default form submission
            handleLogin();
          }}
          className="bg-white p-6 shadow-lg rounded-md max-w-md mx-auto"
        >
          <div className="mb-4">
            <label className="block text-lg font-medium mb-2" htmlFor="email">
              Email
            </label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              required
              className="w-full px-4 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div className="mb-4">
            <label
              className="block text-lg font-medium mb-2"
              htmlFor="password"
            >
              Password
            </label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              className="w-full px-4 py-2 border border-gray-300 rounded-md"
            />
          </div>
          {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
          <button
            type="submit"
            className="w-full bg-primary text-white text-lg py-2 rounded-md mt-4 hover:bg-neutral-dark transition"
          >
            Login
          </button>
          <div className="mt-4 text-center text-gray-600">
            <p>
              Don&apos;t have an account yet?{" "}
              <Link href="/signup" className="text-primary font-semibold hover:underline">
                Sign up
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
