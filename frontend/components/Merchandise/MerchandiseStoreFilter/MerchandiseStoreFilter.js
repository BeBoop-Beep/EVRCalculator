"use client";

export default function MerchandiseStoreFilter({
  categories,
  parents,
  expandedParents,
  groupedChildren,
  selectedChildCategories,
  toggleParent,
  onChildCategorySelect,
  onClearAllFilters,
}) {
  // Check if a parent has any selected children
  const hasSelectedChildren = (parentId) => {
    const childIds = groupedChildren[parentId]?.map((child) => child._id) || [];
    return childIds.some((id) => selectedChildCategories.includes(id));
  };

  return (
    <div className="fixed top-[140px] left-0 w-64 h-[calc(100vh-140px)] bg-[var(--surface-panel)] p-6 overflow-y-auto border-r border-[var(--border-subtle)]">
      <h3 className="text-xl font-semibold text-[var(--text-primary)] mb-6">Filters</h3>

      {/* Render only the filtered parents */}
      {parents.map((parent) => {
        const isExpanded = expandedParents.includes(parent._id);
        const hasChildrenSelected = hasSelectedChildren(parent._id);

        return (
          <div key={parent._id} className="mb-3">
            <label className="flex items-center cursor-pointer font-semibold text-[var(--text-primary)] hover:text-[var(--text-primary)] transition-colors">
              <div className="relative w-5 h-5 mr-3 border border-[var(--border-subtle)] rounded-md flex items-center justify-center transition-all hover:border-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  className="absolute opacity-0 w-full h-full cursor-pointer"
                  checked={isExpanded || hasChildrenSelected}
                  onChange={() => toggleParent(parent._id)}
                />
                {isExpanded ? (
                  <span className="text-[var(--text-primary)] text-sm">-</span>
                ) : hasChildrenSelected ? (
                  <span className="text-[var(--text-primary)] text-sm">✓</span>
                ) : null}
              </div>
              <span>{parent.name}</span>
            </label>

            {isExpanded &&
              groupedChildren[parent._id]?.length > 0 && (
                <div className="ml-6 mt-2 space-y-1">
                  {groupedChildren[parent._id].map((child) => (
                    <label
                      key={child._id}
                      className="flex items-center cursor-pointer text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                    >
                      <div className="relative w-5 h-5 mr-3 border border-[var(--border-subtle)] rounded-md flex items-center justify-center transition-all hover:border-[var(--text-secondary)]">
                        <input
                          type="checkbox"
                          className="absolute opacity-0 w-full h-full cursor-pointer"
                          checked={selectedChildCategories.includes(child._id)}
                          onChange={() => onChildCategorySelect(child._id)}
                        />
                        {selectedChildCategories.includes(child._id) && (
                          <span className="text-[var(--text-primary)] text-sm">✓</span>
                        )}
                      </div>
                      <span>{child.name}</span>
                    </label>
                  ))}
                </div>
              )}
          </div>
        );
      })}

      {/* Clear All Filters Button */}
      {selectedChildCategories.length > 0 && (
        <button
          className="w-full py-2 px-4 bg-[var(--surface-page)] text-[var(--text-secondary)] rounded-md hover:bg-[var(--surface-hover)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--border-subtle)]"
          onClick={onClearAllFilters}
        >
          Clear All Filters
        </button>
      )}
    </div>
  );
}