import Image from "next/image";

export default function InDexLogoLoader({
  fullScreen = true,
  label = "Loading",
  showLabel = false,
  className = "",
}) {
  return (
    <div
      className={`index-loader-shell ${fullScreen ? "index-loader-shell--fullscreen" : ""} ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <div className="index-loader-wrap">
        <div className="index-loader-glow" aria-hidden="true" />

        <div className="index-loader-logo-frame" aria-hidden="true">
          <Image
            src="/images/inDex.png"
            alt=""
            width={128}
            height={128}
            priority
            sizes="(max-width: 640px) 96px, 128px"
            className="index-loader-logo"
          />
        </div>

        <div className="index-loader-dots" aria-hidden="true">
          <span className="index-loader-dot" />
          <span className="index-loader-dot" />
          <span className="index-loader-dot" />
        </div>

        {showLabel ? <p className="index-loader-copy">inDex</p> : null}
      </div>

      <span className="sr-only">{label}</span>
    </div>
  );
}