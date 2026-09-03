import Link from "next/link";

export const metadata = {
  title: "Contact & Support | inDex",
  description: "Contact inDex for account, billing, privacy, or general support.",
};

const SUPPORT_EMAIL = "dengkee.business@gmail.com";

export default function ContactPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6 lg:py-16">
      <header className="border-b border-[var(--border-subtle)] pb-8">
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-[var(--accent)]">
          inDex Support
        </p>
        <h1 className="mt-3 text-4xl font-semibold text-[var(--text-primary)] sm:text-5xl">
          Contact &amp; Support
        </h1>
        <p className="mt-5 text-base leading-7 text-[var(--text-secondary)]">
          For account access, membership billing, privacy questions, refunds, or general support,
          email us at{" "}
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="font-semibold text-[var(--text-primary)] underline underline-offset-4"
          >
            {SUPPORT_EMAIL}
          </a>.
        </p>
      </header>

      <section className="py-10 text-[var(--text-secondary)]">
        <h2 className="text-2xl font-semibold text-[var(--text-primary)]">Billing help</h2>
        <p className="mt-3 leading-7">
          Active subscribers can manage payment methods, invoices, and cancellation from the
          Membership &amp; Billing area in their inDex account. If you cannot access your account or
          need help with a charge, email us and include the email address associated with your inDex
          account. Do not send full card numbers, passwords, or other sensitive credentials.
        </p>

        <h2 className="mt-8 text-2xl font-semibold text-[var(--text-primary)]">Legal &amp; privacy</h2>
        <p className="mt-3 leading-7">
          You can review our <Link href="/terms" className="font-semibold text-[var(--text-primary)] underline underline-offset-4">Terms of Service</Link>,{" "}
          <Link href="/privacy" className="font-semibold text-[var(--text-primary)] underline underline-offset-4">Privacy Policy</Link>, and{" "}
          <Link href="/cookies" className="font-semibold text-[var(--text-primary)] underline underline-offset-4">Cookie Policy</Link> at any time.
        </p>
      </section>
    </main>
  );
}
