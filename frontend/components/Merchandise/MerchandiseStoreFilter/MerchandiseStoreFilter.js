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
    <div className="fixed top-[140px] left-0 w-64 h-[calc(100vh-140px)] bg-white p-6 overflow-y-auto border-r border-gray-200 shadow-lg">
      <h3 className="text-xl font-semibold text-gray-900 mb-6">Filters</h3>

      {/* Render only the filtered parents */}
      {parents.map((parent) => {
        const isExpanded = expandedParents.includes(parent._id);
        const hasChildrenSelected = hasSelectedChildren(parent._id);

        return (
          <div key={parent._id} className="mb-3">
            <label className="flex items-center cursor-pointer font-semibold text-gray-800 hover:text-gray-900 transition-colors">
              <div className="relative w-5 h-5 mr-3 border border-gray-300 rounded-md flex items-center justify-center transition-all hover:border-gray-400">
                <input
                  type="checkbox"
                  className="absolute opacity-0 w-full h-full cursor-pointer"
                  checked={isExpanded || hasChildrenSelected}
                  onChange={() => toggleParent(parent._id)}
                />
                {isExpanded ? (
                  <span className="text-gray-800 text-sm">-</span>
                ) : hasChildrenSelected ? (
                  <span className="text-gray-800 text-sm">✓</span>
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
                      className="flex items-center cursor-pointer text-gray-700 hover:text-gray-900 transition-colors"
                    >
                      <div className="relative w-5 h-5 mr-3 border border-gray-300 rounded-md flex items-center justify-center transition-all hover:border-gray-400">
                        <input
                          type="checkbox"
                          className="absolute opacity-0 w-full h-full cursor-pointer"
                          checked={selectedChildCategories.includes(child._id)}
                          onChange={() => onChildCategorySelect(child._id)}
                        />
                        {selectedChildCategories.includes(child._id) && (
                          <span className="text-gray-800 text-sm">✓</span>
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
          className="w-full py-2 px-4 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400"
          onClick={onClearAllFilters}
        >
          Clear All Filters
        </button>
      )}
    </div>
  );
}