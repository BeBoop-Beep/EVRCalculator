/** @type {import('next').NextConfig} */
const nextConfig = {
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

export default nextConfig;
