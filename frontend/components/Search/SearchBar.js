import { useEffect, useState } from "react";

export default function SearchBar({
  onSearch,
  initialQuery = "",
  className = "flex justify-center my-8",
  inputClassName = "w-1/2 px-4 py-2 border rounded-l-lg focus:outline-none",
  buttonClassName = "bg-black text-white px-6 py-2 rounded-r-lg hover:bg-gray-800 transition-colors",
  placeholder = "Search for a Pokemon TCG product...",
  buttonLabel = "Search",
  inputAutoFocus = false,
}) {
  const [query, setQuery] = useState(initialQuery);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  const handleSearch = () => {
    onSearch(query.trim());
  };

  return (
    <div className={className}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus={inputAutoFocus}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            handleSearch();
          }
        }}
        placeholder={placeholder}
        className={inputClassName}
      />
      <button
        onClick={handleSearch}
        className={buttonClassName}
      >
        {buttonLabel}
      </button>
    </div>
  );
}