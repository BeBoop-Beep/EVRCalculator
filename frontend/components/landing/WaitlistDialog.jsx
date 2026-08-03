"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  isLikelyValidEmail,
  submitWaitlistSignup,
} from "@/lib/waitlist/waitlistSignupServer";
import styles from "./waitlistCta.module.css";

const FEEDBACK_CLASS = {
  success: styles.feedbackSuccess,
  exists: styles.feedbackExists,
  error: styles.feedbackError,
};

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * The waitlist signup, in a dialog.
 *
 * The signup contract is unchanged from the inline hero form this replaces:
 * the same submitWaitlistSignup call, the same status branches, the same
 * resend-verification affordance. Only the container moved, so the landing
 * page can ask for the address at the moment the visitor opts in instead of
 * parking a text field in the first mobile viewport.
 */
export default function WaitlistDialog({ onClose, source = "landing_page" }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [touched, setTouched] = useState(false);
  const [resendEmail, setResendEmail] = useState("");
  const [feedback, setFeedback] = useState(null); // { type: "success"|"exists"|"error", message: string }

  const dialogRef = useRef(null);
  const fieldRef = useRef(null);

  const trimmedEmail = email.trim();
  const isEmailValid = !trimmedEmail || isLikelyValidEmail(trimmedEmail);
  const showInlineInvalid = touched && !!trimmedEmail && !isEmailValid;
  // Only in-flight requests disable the button. An empty or malformed address
  // is answered by handleSignup with "Enter a valid email." rather than by
  // dimming the one yellow element in the dialog before anything is typed.
  const isSubmitDisabled = loading || resending;

  useEffect(() => {
    fieldRef.current?.focus();
  }, []);

  /*
   * Escape is bound on the document, not on the overlay.
   *
   * Bound to the overlay it only fired while focus was still inside the dialog
   * subtree — after a submit re-render moved focus, Escape stopped closing the
   * dialog entirely. A modal must close on Escape wherever focus happens to be.
   */
  useEffect(() => {
    function onEscape(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [onClose]);

  // Tab cycles inside the dialog rather than walking the page behind it.
  const handleKeyDown = useCallback(
    (event) => {
      if (event.key !== "Tab") return;

      const focusable = dialogRef.current?.querySelectorAll(FOCUSABLE);
      if (!focusable || focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    []
  );

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

    const result = await submitWaitlistSignup(currentEmail, source);

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
    const result = await submitWaitlistSignup(targetEmail, source);
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
    <div
      className={styles.overlay}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="waitlist-dialog-title"
      >
        <button type="button" onClick={onClose} className={styles.close} aria-label="Close">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M4 4l8 8M12 4l-8 8"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          </svg>
        </button>

        <p className={styles.dialogHead}>
          <span className={styles.dialogDot} aria-hidden="true" />
          Early access
        </p>
        <h2 id="waitlist-dialog-title" className={styles.dialogTitle}>
          Join the waitlist
        </h2>
        <p className={styles.dialogNote}>
          We&rsquo;ll email you when inDex opens up. One address, one message to confirm it.
        </p>

        <form onSubmit={handleSignup} className={styles.form} noValidate>
          <label className={styles.label} htmlFor="waitlist-dialog-email">
            Email address
          </label>
          <input
            ref={fieldRef}
            id="waitlist-dialog-email"
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
          <button type="submit" disabled={isSubmitDisabled} className={styles.submit}>
            {loading ? "Joining…" : "Join the waitlist"}
          </button>
        </form>

        <div aria-live="polite">
          {showInlineInvalid ? (
            <p className={`${styles.feedback} ${styles.feedbackError}`}>Enter a valid email.</p>
          ) : null}

          {feedback ? (
            <p className={`${styles.feedback} ${FEEDBACK_CLASS[feedback.type] || styles.feedbackError}`}>
              {feedback.message}
            </p>
          ) : null}
        </div>

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
    </div>
  );
}
