import createBundleAnalyzer from "@next/bundle-analyzer";

const withBundleAnalyzer = createBundleAnalyzer({
	enabled: process.env.ANALYZE === "true",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
	// Keep production performance audits isolated from a concurrently running
	// development server, which otherwise rewrites the shared .next directory.
	...(process.env.PERF_AUDIT_DIST_DIR
		? { distDir: process.env.PERF_AUDIT_DIST_DIR }
		: {}),
	// Set/Rankings surfaces use many named Recharts exports. Ask Next to rewrite
	// those package imports to the narrow modules that are actually referenced so
	// an analytical route does not pay to traverse the package barrel graph.
	experimental: {
		optimizePackageImports: ["recharts"],
	},
	images: {
		// EXACTLY the two hosts that serve set/card artwork today — never a
		// wildcard. `/_next/image` is a fetch-and-transform endpoint, so every
		// host listed here is a host this origin will proxy on request.
		//
		// Both serve source PNGs that are wildly larger than the slots they are
		// painted into (a 245x342 RGBA card PNG is ~182 kB and is rendered as
		// small as 40x54 CSS px), so routing them through the optimizer is the
		// single largest image saving available. See
		// `lib/images/remoteImageDelivery.mjs` for the URL builder that must
		// stay in sync with this list.
		remotePatterns: [
			{ protocol: "https", hostname: "images.pokemontcg.io" },
			{ protocol: "https", hostname: "images.scrydex.com" },
		],
	},
	async redirects() {
		return [
			{
				source: "/Explore",
				destination: "/Rankings",
				permanent: true,
			},
			// /Explore/top-10 was a "coming soon" placeholder for ranked set
			// views. /Rankings now IS that view (it was even the placeholder's
			// own call to action), so the URL is redirected rather than left as
			// a thin page competing for the same intent. External links keep
			// working.
			{
				source: "/Explore/top-10",
				destination: "/Rankings",
				permanent: true,
			},
			// NOTE: the legacy set-detail tab aliases (?tab=rip|analysis|
			// analytics) are NOT redirected here. A config redirect re-appends
			// the request's query string to a path destination, so stripping
			// `tab` this way would redirect the alias straight back to itself.
			// They are collapsed onto the bare canonical set URL in
			// middleware.js, which can delete exactly one parameter, keep the
			// rest, and still set a real 308 status.
			// /Research was a top-level product section whose entire content
			// was the RIP methodology. Articles is now the content destination
			// and that methodology is an article inside it, so the old URL is
			// redirected to the article ITSELF — not to the /Articles hub —
			// because every external link to /Research was a link to the
			// methodology. ONE rule covers both spellings: redirect `source`
			// matching is case-insensitive, so this also catches the /research a
			// visitor types by hand or a video description writes lowercase.
			{
				source: "/Research",
				destination: "/Articles/how-rip-score-works",
				permanent: true,
			},
			// NOTE: there is deliberately no /articles -> /Articles rule. Redirect
			// `source` matching is CASE-INSENSITIVE, so such a rule also matches
			// /Articles itself and 308s the canonical URL to itself forever. The
			// pair above is safe only because its destination is a different path
			// than either source. The capitalized hub is the one canonical URL, the
			// same as /Rankings and /Market, neither of which has a lowercase alias.
			{
				source: "/learn",
				destination: "/tools",
				permanent: true,
			},
			{
				source: "/Learn",
				destination: "/tools",
				permanent: true,
			},
			{
				source: "/my-collection",
				destination: "/my-portfolio",
				permanent: true,
			},
			{
				source: "/my-collection/:path*",
				destination: "/my-portfolio/:path*",
				permanent: true,
			},
		];
	},
	async rewrites() {
		return [
			{
				source: "/my-portfolio",
				destination: "/my-collection",
			},
			{
				source: "/my-portfolio/:path*",
				destination: "/my-collection/:path*",
			},
		];
	},
};

export default withBundleAnalyzer(nextConfig);
