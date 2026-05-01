"use client";

import { useState } from "react";
import {
  isLikelyValidEmail,
  submitWaitlistSignup,
} from "@/lib/waitlist/waitlistSignupServer";

export default function Featured({ products }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [touched, setTouched] = useState(false);
  const [resendEmail, setResendEmail] = useState("");
  const [feedback, setFeedback] = useState(null); // { type: "success"|"exists"|"error", message: string }

  const trimmedEmail = email.trim();
  const isEmailValid = !trimmedEmail || isLikelyValidEmail(trimmedEmail);
  const showInlineInvalid = touched && !!trimmedEmail && !isEmailValid;
  const isSubmitDisabled = loading || resending || !trimmedEmail || !isEmailValid;

  async function handleSignup(e) {
    e.preventDefault();
    setTouched(true);
    const currentEmail = String(email || "").trim();
    if (!currentEmail || !isLikelyValidEmail(currentEmail)) {
      setFeedback({ type: "error", message: "Enter a valid email." });
      return;
    }

    setLoading(true);
    setFeedback(null);

    const result = await submitWaitlistSignup(currentEmail);

    setLoading(false);

    if (result.status === "verification_pending" || result.status === "created") {
      setFeedback({ type: "success", message: "Check your email to confirm your spot." });
      setEmail(currentEmail);
      setResendEmail(currentEmail);
    } else if (result.status === "already_exists") {
      setFeedback({ type: "exists", message: "You're already on the list." });
      setResendEmail("");
    } else if (result.status === "already_verified") {
      setFeedback({ type: "exists", message: "You're already on the list." });
      setResendEmail("");
    } else if (result.status === "invalid_email") {
      setFeedback({ type: "error", message: "Enter a valid email." });
      setResendEmail("");
    } else {
      setFeedback({
        type: "error",
        message: result.message || "Something went wrong. Please try again.",
      });
      setResendEmail("");
    }
  }

  async function handleResend() {
    const targetEmail = String(resendEmail || "").trim();
    if (!targetEmail) {
      return;
    }

    setResending(true);
    const result = await submitWaitlistSignup(targetEmail);
    setResending(false);

    if (result.status === "verification_pending" || result.status === "created") {
      setFeedback({
        type: "success",
        message: result.message || "Verification email sent. Check your inbox.",
      });
      return;
    }

    if (result.status === "already_exists" || result.status === "already_verified") {
      setFeedback({ type: "exists", message: "You're already on the list." });
      setResendEmail("");
      return;
    }

    setFeedback({
      type: "error",
      message: result.message || "Something went wrong. Please try again.",
    });

    if (result.status !== "invalid_email") {
      setResendEmail("");
    }
  }

  return (
    <section className="relative w-full min-h-[540px] overflow-hidden bg-[#020817]">
      {/* Radial background gradient */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 520px at 50% -12%, rgba(16, 69, 129, 0.34) 0%, rgba(2, 8, 23, 0) 62%), linear-gradient(180deg, #020817 0%, #06122a 55%, #08152f 100%)",
        }}
      />

      {/* Background logo — sized between previous (too large) and contained (too small) */}
      <div
        className="absolute inset-0 animate-zoom-in opacity-30"
        style={{
          backgroundImage: "url('/images/inDex.png')",
          backgroundSize: "min(80vw, 80vh)",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      />

      {/* Overlay */}
      <div
        className="absolute inset-0 flex items-center justify-center px-4"
        style={{
          background:
            "linear-gradient(180deg, rgba(2, 8, 23, 0.42) 0%, rgba(2, 8, 23, 0.55) 48%, rgba(2, 8, 23, 0.74) 100%)",
        }}
      >
        <div className="text-center text-white w-full max-w-lg">
          <h1
            className="text-5xl font-bold"
            style={{ textShadow: "2px 2px 4px rgba(0, 4, 41, 0.8)" }}
          >
            Welcome to inDex
          </h1>
          <p
            className="text-xl mt-2 font-bold"
            style={{ textShadow: "2px 2px 4px rgb(0, 4, 41)" }}
          >
            Stay in the know, stay in the Dex.
          </p>

          {/* Email signup form */}
          <form onSubmit={handleSignup} className="mt-8 flex flex-col sm:flex-row gap-2 justify-center">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (!touched) setTouched(true);
              }}
              onBlur={() => setTouched(true)}
              placeholder="Enter your email"
              disabled={loading}
              className="
                w-full sm:w-72
                px-4 py-3
                rounded-3xl
                bg-white/10 border border-white/20
                text-white placeholder-white/50
                text-sm
                focus:outline-none focus:ring-2 focus:ring-yellow-100/60
                transition
                disabled:opacity-50
              "
            />
            <button
              type="submit"
              disabled={isSubmitDisabled}
              className="
                px-6 py-3
                bg-yellow-100 text-primary
                font-semibold rounded-3xl
                shadow-lg hover:bg-accent
                transition duration-300
                disabled:opacity-60 disabled:cursor-not-allowed
                whitespace-nowrap
              "
            >
              {loading ? "Joining…" : "Join the waitlist"}
            </button>
          </form>

          {showInlineInvalid && (
            <p className="mt-2 text-sm font-medium text-red-300">Enter a valid email.</p>
          )}

          {/* Feedback message */}
          {feedback && (
            <p
              className={`mt-3 text-sm font-medium ${
                feedback.type === "success"
                  ? "text-green-300"
                  : feedback.type === "exists"
                  ? "text-yellow-200"
                  : "text-red-300"
              }`}
            >
              {feedback.message}
            </p>
          )}

          {resendEmail && feedback?.type === "success" && (
            <button
              type="button"
              onClick={handleResend}
              disabled={loading || resending}
              className="mt-2 text-sm text-white/75 underline underline-offset-2 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {resending ? "Resending..." : "Resend verification email"}
            </button>
          )}

          {/* Explore CTA */}
          <div className="mt-5">
            <a
              href="/Explore"
              className="text-sm text-white/60 hover:text-white underline underline-offset-2 transition"
            >
              Explore inDex →
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
