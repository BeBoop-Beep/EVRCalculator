import PublicBinderViewer from "@/components/Profile/PublicBinderViewer";

// Mock data generator - creates realistic binder pages
function generateMockBinderPages(username) {
  const seed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);

  // Generate 3-5 binder pages
  const pageCount = 3 + (seed % 3);
  const pages = [];

  for (let p = 0; p < pageCount; p++) {
    const slots = [];
    // Each page has 12 slots (6 per row × 2 rows)
    for (let s = 0; s < 12; s++) {
      // About 70% filled
      if (Math.random() > 0.3) {
        slots.push({
          name: `Card Slot ${s + 1}`,
          imageUrl: null,
          isFoil: Math.random() > 0.8,
        });
      } else {
        slots.push(null); // Empty slot
      }
    }

    pages.push({
      title: `Page ${p + 1}`,
      section: `${["Holos", "Rares", "Commons", "Specials"][p % 4]}`,
      slots: slots,
      cardCount: slots.filter((s) => s !== null).length,
      binderValue: `$${Math.floor(Math.random() * 2000) + 500}`,
    });
  }

  return pages;
}

export default async function PublicBinderPage({ params }) {
  const { username } = await params;

  // Generate mock binder pages
  const binderPages = generateMockBinderPages(username);

  return (
    <div className="space-y-6">
        {/* Info Panel */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            Collectors curate their favorite cards into organized binder pages. Use the navigation to browse through different sections and showcase pieces.
          </p>
        </div>

        {/* Binder Viewer */}
        <PublicBinderViewer
          binderPages={binderPages}
          emptyMessage="This collector hasn't shared any binder pages yet."
        />

        {/* Binder Info */}
        <div className="grid gap-4 sm:grid-cols-2">
          <InfoCard
            title="About This Binder"
            content="High-end collection featuring multiple pages organized by rarity and set."
          />
          <InfoCard
            title="Organization Style"
            content="Organized by rarity level and acquisition date for optimal display."
          />
        </div>
    </div>
  );
}

function InfoCard({ title, content }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4">
      <h3 className="font-semibold text-[var(--text-primary)]">{title}</h3>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">{content}</p>
    </div>
  );
}
