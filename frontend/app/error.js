"use client";

import { useEffect } from "react";

export default function Error({ error, reset }) {
  useEffect(() => {
    console.error("App route error:", error);
  }, [error]);

  return (
    <div className="min-h-[50vh] flex items-center justify-center px-6 py-16">
      <div className="max-w-xl w-full rounded-xl border border-gray-200 bg-white p-8 shadow-sm text-center">
        <h2 className="text-2xl font-bold text-primary mb-3">Something went wrong</h2>
        <p className="text-gray-600 mb-6">An unexpected error occurred while loading this page.</p>
        <button
          type="button"
          onClick={() => reset()}
          className="inline-flex items-center justify-center rounded-md bg-brand px-5 py-2.5 font-semibold text-white hover:bg-brand-dark transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
