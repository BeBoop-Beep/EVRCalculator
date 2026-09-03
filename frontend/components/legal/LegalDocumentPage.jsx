import Link from "next/link";

export const LEGAL_CONTACT_EMAIL = "support@inthedex.io";

export default function LegalDocumentPage({ title, updated, intro, children }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-12 sm:px-6 lg:py-16">
      <header className="border-b border-[var(--border-subtle)] pb-8">
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-[var(--accent)]">
          inDex Legal
        </p>
        <h1 className="mt-3 text-4xl font-semibold text-[var(--text-primary)] sm:text-5xl">
          {title}
        </h1>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Effective and last updated: {updated}
        </p>
        {intro ? (
          <p className="mt-6 max-w-3xl text-base leading-7 text-[var(--text-secondary)]">
            {intro}
          </p>
        ) : null}
      </header>

      <article className="space-y-10 py-10 text-[var(--text-secondary)] [&_a]:font-semibold [&_a]:text-[var(--text-primary)] [&_a]:underline [&_a]:underline-offset-4 [&_h2]:text-2xl [&_h2]:font-semibold [&_h2]:text-[var(--text-primary)] [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-[var(--text-primary)] [&_li]:leading-7 [&_p]:leading-7 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-6">
        {children}
      </article>

      <footer className="border-t border-[var(--border-subtle)] pt-6 text-sm text-[var(--text-secondary)]">
        <p>
          Questions about these terms or policies can be sent to{" "}
          <a href={`mailto:${LEGAL_CONTACT_EMAIL}`}>{LEGAL_CONTACT_EMAIL}</a>.
        </p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link href="/terms">Terms of Service</Link>
          <Link href="/privacy">Privacy Policy</Link>
          <Link href="/cookies">Cookie Policy</Link>
          <Link href="/pricing">Membership Pricing</Link>
        </div>
      </footer>
    </main>
  );
}
