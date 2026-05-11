'use client';

import { useState, useEffect, useRef } from 'react';

/**
 * Hook to prevent loading indicator flash on fast cached transitions
 * 
 * Behavior:
 * - Delays showing the loader by showDelayMs (default 200ms)
 * - If loading completes before the delay, loader never shows
 * - Once shown, keeps loader visible for minVisibleMs (default 450ms) minimum
 * - Handles rapid loading state changes gracefully
 * - Cleans up all timers on unmount
 * 
 * @param {boolean} isLoading - Whether content is loading
 * @param {Object} options - Configuration options
 * @param {number} options.showDelayMs - Delay before showing loader (default: 200)
 * @param {number} options.minVisibleMs - Minimum time loader stays visible (default: 450)
 * @returns {boolean} shouldShowLoader - Whether to show the loader
 */
export function useDelayedLoader(
  isLoading,
  { showDelayMs = 200, minVisibleMs = 450 } = {}
) {
  const [shouldShowLoader, setShouldShowLoader] = useState(false);
  const showTimerRef = useRef(null);
  const minVisibleTimerRef = useRef(null);
  const loaderVisibleAtRef = useRef(null);

  useEffect(() => {
    // Clean up existing timers when dependencies change
    const cleanupTimers = () => {
      if (showTimerRef.current) {
        clearTimeout(showTimerRef.current);
        showTimerRef.current = null;
      }
      if (minVisibleTimerRef.current) {
        clearTimeout(minVisibleTimerRef.current);
        minVisibleTimerRef.current = null;
      }
    };

    if (isLoading) {
      // Loading started: set up delayed show
      cleanupTimers();
      loaderVisibleAtRef.current = null;
      setShouldShowLoader(false);

      showTimerRef.current = setTimeout(() => {
        setShouldShowLoader(true);
        loaderVisibleAtRef.current = Date.now();
        showTimerRef.current = null;
      }, showDelayMs);
    } else {
      // Loading finished: determine if we need to keep loader visible
      if (loaderVisibleAtRef.current) {
        // Loader was shown - respect minVisibleMs
        const visibleDuration = Date.now() - loaderVisibleAtRef.current;
        const remainingMinDuration = Math.max(0, minVisibleMs - visibleDuration);

        if (remainingMinDuration > 0) {
          // Keep loader visible for remaining time
          minVisibleTimerRef.current = setTimeout(() => {
            setShouldShowLoader(false);
            loaderVisibleAtRef.current = null;
            minVisibleTimerRef.current = null;
          }, remainingMinDuration);
        } else {
          // Already visible long enough, hide immediately
          setShouldShowLoader(false);
          loaderVisibleAtRef.current = null;
        }
      }

      // Cancel the show timer if we haven't shown yet
      cleanupTimers();
    }

    return cleanupTimers;
  }, [isLoading, showDelayMs, minVisibleMs]);

  return shouldShowLoader;
}
