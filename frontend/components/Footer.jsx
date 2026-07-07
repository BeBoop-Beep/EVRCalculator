import Image from "next/image";
import Link from "next/link";

const NAV_COLUMNS = [
  {
    heading: "Product",
    links: [
      { label: "Explore", href: "/Explore" },
      { label: "TCGs", href: "/TCGs" },
      { label: "Tools", href: "/tools" },
      { label: "My Portfolio", href: "/my-collection" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Blog", href: "/blog" },
      { label: "Careers", href: "/careers" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Terms of Service", href: "/terms" },
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Cookie Policy", href: "/cookies" },
    ],
  },
  {
    heading: "Support",
    links: [
      { label: "Help Center", href: "/help" },
      { label: "Contact Us", href: "/contact-us" },
      { label: "Status", href: "/status" },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="border-t border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)]">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:px-8">
        {/* Main grid */}
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
          {/* Brand column */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Image
                src="/images/inDex.png"
                alt="inDex logo"
                width={40}
                height={40}
                className="rounded-sm opacity-90"
              />
              <span className="text-base font-semibold text-[var(--text-primary)]">inDex</span>
            </div>
            <p className="text-sm leading-relaxed">
              The intelligence layer for collectible portfolios.
            </p>
            <p className="text-sm leading-relaxed">
              Built for collectors who think like investors.
            </p>
          </div>

          {/* Nav columns */}
          {NAV_COLUMNS.map((col) => (
            <div key={col.heading}>
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-primary)]">
                {col.heading}
              </p>
              <ul className="space-y-3">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-sm transition-colors hover:text-[var(--text-primary)]"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom row */}
        <div className="mt-12 border-t border-[var(--border-subtle)] pt-6">
          <div className="text-center text-xs text-[var(--text-secondary)]">
            © {new Date().getFullYear()} inDex. All rights reserved.
          </div>
          <div className="mx-auto mt-4 max-w-3xl text-center text-[11px] leading-relaxed text-[var(--text-secondary)]">
            <p>
              Pricing and simulation results are estimates for informational and entertainment purposes only. Pricing inputs use third-party market snapshots where available and may be incomplete, delayed, inaccurate, or change without notice. inDex is not endorsed, certified, sponsored, or affiliated with any marketplace, card manufacturer, grading company, or rights holder referenced on this site.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
