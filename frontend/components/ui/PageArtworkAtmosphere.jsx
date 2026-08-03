export default function PageArtworkAtmosphere({
  src,
  dataAttribute = "data-page-ambient-artwork",
  visibilityClassName = "hidden sm:block",
  loading = "eager",
}) {
  if (!src) {
    return null;
  }

  return (
    <div
      {...{ [dataAttribute]: true }}
      aria-hidden="true"
      className={`set-page-atmosphere pointer-events-none fixed inset-0 -z-10 select-none overflow-hidden bg-no-repeat ${visibilityClassName}`}
    >
      <img
        src={src}
        alt=""
        className="set-page-atmosphere-bloom absolute inset-0 h-full w-full object-contain object-center"
        loading={loading}
        decoding="async"
      />
      <img
        src={src}
        alt=""
        className="set-page-atmosphere-artwork absolute inset-0 h-full w-full object-contain object-center"
        loading={loading}
        decoding="async"
      />
    </div>
  );
}
