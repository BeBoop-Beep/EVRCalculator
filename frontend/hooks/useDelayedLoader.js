'use client';

import { useState, useEffect, useRef } from 'react';
import {
  FULL_LOADER_DELAY_MS,
  MIN_FULL_LOADER_VISIBLE_MS,
  debugLoadingTiming,
} from "@/lib/navigation/loadingPolicy";

/**
 * Hook to prevent loading indicator flash on fast cached transitions
 * 
 * Behavior:
 * - Delays showing the loader by showDelayMs (default 700ms)
 * - If loading completes before the delay, loader never shows
 * - Once shown, keeps loader visible for minVisibleMs (default 400ms) minimum
 * - Handles rapid loading state changes gracefully
 * - Cleans up all timers on unmount
 * 
 * @param {boolean} isLoading - Whether content is loading
 * @param {Object} options - Configuration options
 * @param {number} options.showDelayMs - Delay before showing loader (default: 700)
 * @param {number} options.minVisibleMs - Minimum time loader stays visible (default: 400)
 * @param {string} options.debugLabel - Development-only label for timing logs
 * @returns {boolean} shouldShowLoader - Whether to show the loader
 */
export function useDelayedLoader(
  isLoading,
  {
    showDelayMs = FULL_LOADER_DELAY_MS,
    minVisibleMs = MIN_FULL_LOADER_VISIBLE_MS,
    debugLabel = "full-loader",
  } = {}
) {
  const [shouldShowLoader, setShouldShowLoader] = useState(false);
  const showTimerRef = useRef(null);
  const minVisibleTimerRef = useRef(null);
  const loaderVisibleAtRef = useRef(null);
  const loadingStartedAtRef = useRef(null);

  useEffect(() => {
    const clearShowTimer = () => {
      if (showTimerRef.current) {
        clearTimeout(showTimerRef.current);
        showTimerRef.current = null;
      }
    };

    const clearMinVisibleTimer = () => {
      if (minVisibleTimerRef.current) {
        clearTimeout(minVisibleTimerRef.current);
        minVisibleTimerRef.current = null;
      }
    };

    if (isLoading) {
      clearShowTimer();
      clearMinVisibleTimer();
      loadingStartedAtRef.current = Date.now();
      loaderVisibleAtRef.current = null;
      setShouldShowLoader(false);
      debugLoadingTiming("navigation_start", { label: debugLabel, delayMs: showDelayMs });

      showTimerRef.current = setTimeout(() => {
        debugLoadingTiming("branded_loader_threshold_reached", {
          label: debugLabel,
          elapsedMs: loadingStartedAtRef.current ? Date.now() - loadingStartedAtRef.current : null,
        });
        setShouldShowLoader(true);
        loaderVisibleAtRef.current = Date.now();
        showTimerRef.current = null;
        debugLoadingTiming("branded_loader_shown", { label: debugLabel });
      }, showDelayMs);
    } else {
      clearShowTimer();

      if (loaderVisibleAtRef.current) {
        const visibleDuration = Date.now() - loaderVisibleAtRef.current;
        const remainingMinDuration = Math.max(0, minVisibleMs - visibleDuration);

        if (remainingMinDuration > 0) {
          clearMinVisibleTimer();
          minVisibleTimerRef.current = setTimeout(() => {
            setShouldShowLoader(false);
            loaderVisibleAtRef.current = null;
            minVisibleTimerRef.current = null;
            debugLoadingTiming("branded_loader_hidden", { label: debugLabel });
          }, remainingMinDuration);
        } else {
          setShouldShowLoader(false);
          loaderVisibleAtRef.current = null;
          debugLoadingTiming("branded_loader_hidden", { label: debugLabel });
        }
      } else {
        setShouldShowLoader(false);
      }
      loadingStartedAtRef.current = null;
    }

    return () => {
      clearShowTimer();
      clearMinVisibleTimer();
    };
  }, [isLoading, showDelayMs, minVisibleMs, debugLabel]);

  return shouldShowLoader;
}
