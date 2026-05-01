import Link from "next/link";

export default function SignupInviteOnlyPage() {
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-16 sm:px-6">
      <div className="dashboard-container">
        <div className="mx-auto max-w-xl rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8 text-center">
          <h1 className="text-3xl font-bold text-[var(--text-primary)] sm:text-4xl">
            Account creation is invite-only
          </h1>
          <p className="mt-4 text-[var(--text-secondary)]">
            New account creation is currently closed while we prepare the platform. Join the early-access list from
            the homepage to be notified when access opens.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link
              href="/"
              className="inline-flex items-center justify-center rounded-md bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors duration-200 ease-in-out hover:bg-brand-dark"
            >
              Back to home
            </Link>
            <Link
              href="/#waitlist"
              className="inline-flex items-center justify-center rounded-md border border-[var(--border-subtle)] px-5 py-2.5 text-sm font-semibold text-[var(--text-secondary)] transition-colors duration-200 ease-in-out hover:bg-[var(--surface-hover)]"
            >
              Join early access
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}