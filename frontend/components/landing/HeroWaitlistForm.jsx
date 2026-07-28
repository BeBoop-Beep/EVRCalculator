"use client";

import { useState } from "react";
import Link from "next/link";
import {
  isLikelyValidEmail,
  submitWaitlistSignup,
} from "@/lib/waitlist/waitlistSignupServer";
import styles from "./LandingHero.module.css";

const FEEDBACK_CLASS = {
  success: styles.feedbackSuccess,
  exists: styles.feedbackExists,
  error: styles.feedbackError,
};

export default function HeroWaitlistForm() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [touched, setTouched] = useState(false);
  const [resendEmail, setResendEmail] = useState("");
  const [feedback, setFeedback] = useState(null); // { type: "success"|"exists"|"error", message: string }

  const trimmedEmail = email.trim();
  const isEmailValid = !trimmedEmail || isLikelyValidEmail(trimmedEmail);
  const showInlineInvalid = touched && !!trimmedEmail && !isEmailValid;
  // Only in-flight requests disable the button. An empty or malformed address
  // is answered by handleSignup with "Enter a valid email." — dimming the one
  // yellow element on the page before the visitor has typed anything would put
  // the hero's primary action at half strength on first paint.
  const isSubmitDisabled = loading || resending;

  async function handleSignup(event) {
    event.preventDefault();
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
    } else if (result.status === "already_exists" || result.status === "already_verified") {
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
    <div className={styles.ctas}>
      <form onSubmit={handleSignup} className={styles.form} noValidate>
        <label className="sr-only" htmlFor="hero-waitlist-email">
          Email address
        </label>
        <input
          id="hero-waitlist-email"
          type="email"
          required
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            if (!touched) setTouched(true);
          }}
          onBlur={() => setTouched(true)}
          placeholder="you@example.com"
          disabled={loading}
          aria-invalid={showInlineInvalid || undefined}
          className={styles.field}
        />
        <button type="submit" disabled={isSubmitDisabled} className={styles.ctaPrimary}>
          {loading ? "Joining…" : "Join the waitlist"}
        </button>
      </form>

      <Link href="/Explore" className={styles.ctaSecondary}>
        Explore set rankings
        <svg
          className={styles.ctaArrow}
          width="13"
          height="13"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M3 8h10M9 4l4 4-4 4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Link>

      {showInlineInvalid ? (
        <p className={`${styles.feedback} ${styles.feedbackError}`}>Enter a valid email.</p>
      ) : null}

      {feedback ? (
        <p className={`${styles.feedback} ${FEEDBACK_CLASS[feedback.type] || styles.feedbackError}`}>
          {feedback.message}
        </p>
      ) : null}

      {resendEmail && feedback?.type === "success" ? (
        <button
          type="button"
          onClick={handleResend}
          disabled={loading || resending}
          className={styles.resend}
        >
          {resending ? "Resending…" : "Resend verification email"}
        </button>
      ) : null}
    </div>
  );
}
