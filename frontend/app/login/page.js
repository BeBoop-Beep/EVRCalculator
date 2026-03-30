"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [infoMessage, setInfoMessage] = useState("");
  const [isResending, setIsResending] = useState(false);
  const router = useRouter();

  const handleLogin = async () => {
    try {
      setError(null);
      setInfoMessage("");

      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
        credentials: "include", // Ensure cookies are sent and received automatically
      });

      if (response.ok) {
        // Since token is handled by the server (set in cookies), no need to store it on frontend
        router.push("/profile"); // Redirect to profile after login
      } else {
        const errorData = await response.json();
        setError(errorData?.message || "Invalid credentials.");
      }
    } catch (error) {
      console.error("Login error:", error); // Log the actual error for debugging
      setError("An error occurred while logging in.");
    }
  };

  const shouldShowResendConfirmation =
    typeof error === "string" && error.toLowerCase().includes("email not confirmed");

  const handleResendConfirmation = async () => {
    try {
      setIsResending(true);
      setInfoMessage("");

      const response = await fetch("/api/resend-confirmation", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });

      const data = await response.json();
      if (!response.ok) {
        setError(data?.message || "Unable to resend confirmation email.");
        return;
      }

      setInfoMessage(data?.message || "Confirmation email sent. Please check your inbox and spam folder.");
    } catch (resendError) {
      setError("An error occurred while resending confirmation email.");
    } finally {
      setIsResending(false);
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
          <h2 className="text-4xl font-bold text-center text-[var(--text-primary)] mb-6">
          Login
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault(); // Prevent default form submission
            handleLogin();
          }}
            className="bg-[var(--surface-panel)] p-6 rounded-md border border-[var(--border-subtle)] max-w-md mx-auto"
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
                className="w-full px-4 py-2 border border-[var(--border-subtle)] rounded-md bg-[var(--surface-page)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
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
                className="w-full px-4 py-2 border border-[var(--border-subtle)] rounded-md bg-[var(--surface-page)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
          </div>
          {error && <p className="text-red-500 text-sm mb-4">{error}</p>}
          {infoMessage && <p className="text-green-700 text-sm mb-4">{infoMessage}</p>}
          {shouldShowResendConfirmation ? (
            <button
              type="button"
              onClick={handleResendConfirmation}
              disabled={isResending}
                className="mb-4 inline-flex rounded-md border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isResending ? "Sending..." : "Resend confirmation email"}
            </button>
          ) : null}
          <button
            type="submit"
            className="w-full bg-brand text-white text-lg py-2 rounded-md mt-4 hover:bg-brand-dark transition-colors duration-200 ease-in-out font-semibold"
          >
            Login
          </button>
          <div className="mt-4 text-center text-[var(--text-secondary)]">
            <p>
              Don&apos;t have an account yet?{" "}
              <Link href="/signup" className="text-accent font-semibold hover:underline transition-colors duration-200 ease-in-out">
                Sign up
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
