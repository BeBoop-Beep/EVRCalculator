"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import WaitlistDialog from "./WaitlistDialog";
import styles from "./waitlistCta.module.css";

/**
 * "Join the waitlist" — the page's one primary action, in both the hero and the
 * final CTA. The dialog mounts only once opened, so the closed state costs the
 * first paint a button and nothing else.
 */
/**
 * `variant` is the button's weight in the page's action hierarchy:
 *   "primary" - the yellow pill, used once, in the final CTA
 *   "link"    - a quiet tertiary link, used in the hero where Explore is the
 *               loud action and the waitlist is for an unshipped product
 */
export default function WaitlistCta({
  className = "",
  source = "landing_page",
  label = "Join the waitlist",
  variant = "primary",
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);

  const close = useCallback(() => setOpen(false), []);

  // Return focus to the button that opened the dialog, and stop the page behind
  // it from scrolling while it is up.
  useEffect(() => {
    if (!open) return undefined;
    // The trigger is captured while the dialog is open so the cleanup restores
    // focus to the button that was actually pressed.
    const trigger = triggerRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [open]);

  return (
    <div className={styles.root}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        /* The caller owns how the button sits in ITS layout (flex basis on a
           phone, auto on desktop); this component owns how it looks. */
        className={`${variant === "link" ? styles.triggerLink : styles.trigger} ${className}`.trim()}
      >
        {label}
      </button>
      {/*
        Portalled to <body> deliberately. The hero's entrance animation is a
        filled transform on the container this button sits in, which makes that
        container the containing block for `position: fixed` — the overlay came
        out sized to the button row rather than to the viewport. Rendering the
        dialog outside that subtree is the fix, and it is the right place for a
        modal regardless.
      */}
      {open ? createPortal(<WaitlistDialog onClose={close} source={source} />, document.body) : null}
    </div>
  );
}
