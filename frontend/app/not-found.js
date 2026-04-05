import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center px-6 py-16">
      <div className="max-w-xl w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8 text-center">
        <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-3">Page not found</h2>
        <p className="text-[var(--text-secondary)] mb-6">The page you requested does not exist.</p>
        <Link
          href="/"
          className="inline-flex items-center justify-center rounded-md bg-brand px-5 py-2.5 font-semibold text-white hover:bg-brand-dark transition-colors"
        >
          Back home
        </Link>
      </div>
    </div>
  );
}
