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
