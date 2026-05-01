import Link from "next/link";
import Footer from "@/components/Footer";

const VARIANT_STYLES = {
  feature: {
    badge: "Feature Preview",
    badgeClass: "border-[var(--accent)]/35 bg-[var(--accent)]/10 text-[var(--accent)]",
  },
  legal: {
    badge: "Legal",
    badgeClass: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)]",
  },
  default: {
    badge: "Coming Soon",
    badgeClass: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)]",
  },
};

export default function ComingSoonPage({
  title,
  body,
  variant = "default",
  ctaLabel = "Back to home",
  ctaHref = "/",
}) {
  const style = VARIANT_STYLES[variant] || VARIANT_STYLES.default;

  return (
    <div className="flex min-h-full flex-col">
      <main className="relative flex min-h-[calc(100vh-var(--app-header-offset,64px))] items-center justify-center overflow-hidden px-4 py-10 sm:px-6 lg:px-8">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(1200px 500px at 50% -12%, rgba(250, 204, 21, 0.09), transparent 65%), radial-gradient(1000px 450px at 50% 120%, rgba(5, 150, 105, 0.08), transparent 70%)",
          }}
        />

        <section className="relative w-full max-w-2xl rounded-2xl border border-[var(--border-subtle)] bg-[rgba(16,27,45,0.72)] px-6 py-8 shadow-[0_20px_45px_rgba(0,0,0,0.35)] backdrop-blur-md sm:px-10 sm:py-12">
          <div className="mx-auto text-center">
            <p
              className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-[0.12em] ${style.badgeClass}`}
            >
              {style.badge}
            </p>

            <h1 className="mt-5 text-3xl font-semibold text-[var(--text-primary)] sm:text-4xl">{title}</h1>

            <p className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)] sm:text-base">{body}</p>

            <div className="mt-8">
              <Link
                href={ctaHref}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                {ctaLabel}
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
