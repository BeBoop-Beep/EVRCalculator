import { useEffect, useState } from "react";

export default function SearchBar({
  onSearch,
  initialQuery = "",
  className = "flex justify-center my-8",
  inputClassName = "w-1/2 px-4 py-2 border rounded-l-lg focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out",
  buttonClassName = "bg-brand text-white px-6 py-2 rounded-r-lg hover:bg-brand-dark hover:shadow-lg transition-all duration-200 ease-in-out font-semibold",
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
        aria-label="Search"
      >
        <svg className="w-[22px] h-[22px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </button>
    </div>
  );
}