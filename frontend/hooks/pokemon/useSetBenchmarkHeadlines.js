"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { readCurrentSetHeadlines } from "@/lib/rankings/ripBenchmarkClient.mjs";

const cache = new Map();
const load = (setId, force) => {
  if (force) cache.delete(setId);
  if (!cache.has(setId)) cache.set(setId, readCurrentSetHeadlines([setId]).catch((error) => { cache.delete(setId); throw error; }));
  return cache.get(setId);
};

export default function useSetBenchmarkHeadlines(setId) {
  const [state, setState] = useState({ setId: null, status: "idle", payload: null, error: null });
  const requestVersion = useRef(0);
  const request = useCallback((force = false) => {
    const version = ++requestVersion.current;
    if (!setId) {
      setState({ setId: null, status: "idle", payload: null, error: null });
      return;
    }
    setState({ setId, status: "loading", payload: null, error: null });
    load(String(setId), force)
      .then((payload) => {
        if (requestVersion.current === version) setState({ setId, status: "ready", payload, error: null });
      })
      .catch((error) => {
        if (requestVersion.current === version) setState({ setId, status: "error", payload: null, error: error.message });
      });
  }, [setId]);
  useEffect(() => {
    request(false);
    return () => { requestVersion.current += 1; };
  }, [request]);
  return { ...state, retry: () => request(true) };
}
