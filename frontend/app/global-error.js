"use client";

export default function GlobalError({ error, reset }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[var(--surface-page)] flex items-center justify-center px-6 py-16">
        <div className="max-w-xl w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8 text-center">
          <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-3">Application error</h2>
          <p className="text-[var(--text-secondary)] mb-6">A critical error occurred. Please try reloading.</p>
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex items-center justify-center rounded-md bg-brand px-5 py-2.5 font-semibold text-white hover:bg-brand-dark transition-colors"
          >
            Reload
          </button>
          {process.env.NODE_ENV !== "production" && error?.message ? (
            <pre className="mt-6 text-left text-xs text-[var(--text-secondary)] whitespace-pre-wrap break-words">
              {error.message}
            </pre>
          ) : null}
        </div>
      </body>
    </html>
  );
}
