"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import {
  LIGHTWEIGHT_FEEDBACK_MAX_VISIBLE_MS,
  LIGHTWEIGHT_FEEDBACK_MIN_VISIBLE_MS,
  debugLoadingTiming,
} from "@/lib/navigation/loadingPolicy";

function getRouteKey(pathname, searchParams) {
  const query = searchParams?.toString?.() || "";
  return `${pathname || ""}${query ? `?${query}` : ""}`;
}

function getInternalHref(anchor) {
  if (!anchor || typeof window === "undefined") {
    return null;
  }
  if (anchor.target && anchor.target !== "_self") {
    return null;
  }
  if (anchor.hasAttribute("download")) {
    return null;
  }

  const url = new URL(anchor.href, window.location.href);
  if (url.origin !== window.location.origin) {
    return null;
  }

  const currentRoute = `${window.location.pathname}${window.location.search}`;
  const nextRoute = `${url.pathname}${url.search}`;
  return nextRoute === currentRoute ? null : nextRoute;
}

export default function RouteTransitionFeedback() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentRouteKey = getRouteKey(pathname, searchParams);
  const [isVisible, setIsVisible] = useState(false);
  const pendingRef = useRef(null);
  const hideTimerRef = useRef(null);
  const timeoutRef = useRef(null);
  const previousRouteKeyRef = useRef(currentRouteKey);

  useEffect(() => {
    window.__INDEX_APP_SHELL_READY__ = true;
  }, []);

  useEffect(() => {
    const clearTimers = () => {
      if (hideTimerRef.current) {
        window.clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    const finishFeedback = ({ reason = "route-ready" } = {}) => {
      const pending = pendingRef.current;
      if (!pending) {
        return;
      }

      clearTimers();
      debugLoadingTiming("destination_route_shell_ready", {
        href: pending.href,
        reason,
        elapsedMs: Math.round(performance.now() - pending.startedAt),
      });

      const visibleFor = performance.now() - pending.visibleAt;
      const remaining = Math.max(0, LIGHTWEIGHT_FEEDBACK_MIN_VISIBLE_MS - visibleFor);
      hideTimerRef.current = window.setTimeout(() => {
        setIsVisible(false);
        pendingRef.current = null;
        hideTimerRef.current = null;
      }, remaining);
    };

    const startFeedback = ({ href = null, source = "navigation" } = {}) => {
      const startedAt = performance.now();
      pendingRef.current = {
        href,
        source,
        startedAt,
        visibleAt: startedAt,
      };
      setIsVisible(true);
      debugLoadingTiming("click_navigation_start", { href, source });
      debugLoadingTiming("lightweight_feedback_shown", { href, source });

      clearTimers();
      timeoutRef.current = window.setTimeout(() => {
        finishFeedback({ reason: "timeout" });
      }, LIGHTWEIGHT_FEEDBACK_MAX_VISIBLE_MS);
    };

    const handleDocumentClick = (event) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      if (event.button !== undefined && event.button !== 0) {
        return;
      }

      const anchor = event.target?.closest?.("a[href]");
      const href = getInternalHref(anchor);
      if (!href) {
        return;
      }

      startFeedback({ href, source: "link-click" });
    };

    const handleNavigationStart = (event) => {
      startFeedback({
        href: event.detail?.href || null,
        source: event.detail?.source || "programmatic",
      });
    };

    document.addEventListener("click", handleDocumentClick, true);
    window.addEventListener("index:navigation-start", handleNavigationStart);

    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
      window.removeEventListener("index:navigation-start", handleNavigationStart);
      clearTimers();
    };
  }, []);

  useEffect(() => {
    if (previousRouteKeyRef.current === currentRouteKey) {
      return;
    }
    previousRouteKeyRef.current = currentRouteKey;

    if (!pendingRef.current) {
      debugLoadingTiming("destination_route_shell_ready", { href: currentRouteKey, reason: "route-change" });
      return;
    }

    const pending = pendingRef.current;
    debugLoadingTiming("destination_route_shell_ready", {
      href: pending.href || currentRouteKey,
      reason: "route-change",
      elapsedMs: Math.round(performance.now() - pending.startedAt),
    });

    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    const visibleFor = performance.now() - pending.visibleAt;
    const remaining = Math.max(0, LIGHTWEIGHT_FEEDBACK_MIN_VISIBLE_MS - visibleFor);
    hideTimerRef.current = window.setTimeout(() => {
      setIsVisible(false);
      pendingRef.current = null;
      hideTimerRef.current = null;
    }, remaining);
  }, [currentRouteKey]);

  return (
    <div
      className={`route-transition-feedback ${isVisible ? "route-transition-feedback--visible" : ""}`}
      aria-hidden="true"
    >
      <span className="route-transition-feedback__bar" />
    </div>
  );
}
