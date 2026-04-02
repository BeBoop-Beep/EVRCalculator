import SharedCollectionGrid from "@/components/Profile/SharedCollectionGrid";

/**
 * Public-facing collection grid component
 * Thin wrapper around SharedCollectionGrid for public collections
 * Always in continuous scroll mode, read-only context
 */
export default function PublicCollectionGrid({
  items = [],
  emptyMessage = "No items to display.",
  variant = "detailed",
  isLoading = false,
  className = "",
}) {
  return (
    <SharedCollectionGrid
      items={items}
      viewMode="continuous"
      variant={variant}
      emptyMessage={emptyMessage}
      isLoading={isLoading}
      isPublic={true}
      className={className}
    />
  );
}
