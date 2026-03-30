'use client';
import Link from "next/link";
import { usePathname } from 'next/navigation';

export default function SecondaryNav({ basePath = "/TCGs/Pokemon" }) {
  const pathname = usePathname();

  const navItems = [
    { label: "Overview", path: basePath },
    { label: "Sets", path: `${basePath}/Sets` },
    { label: "Analytics", path: `${basePath}/Analytics` },
  ];

  const isActive = (path) => {
    if (path === basePath) {
      return pathname === basePath || pathname === `${basePath}/`;
    }
    return pathname.startsWith(path);
  };

  return (
    <nav className="bg-[var(--surface-page)] border-b border-[var(--border-subtle)]">
      <div className="w-full px-2 md:px-6 lg:px-10">
        <div className="flex items-center">
          {navItems.map((item, index) => (
            <div key={item.path} className="flex items-center">
              <Link
                href={item.path}
                className={`px-4 md:px-6 py-4 text-sm md:text-base font-medium transition-colors duration-200 hover:bg-[var(--surface-hover)] ${
                  isActive(item.path)
                    ? "text-[var(--accent)] border-b-2 border-[var(--accent)] font-semibold"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {item.label}
              </Link>
              {index < navItems.length - 1 && (
                <div className="h-6 w-px bg-[var(--border-subtle)]"></div>
              )}
            </div>
          ))}
        </div>
      </div>
    </nav>
  );
}
