/** @type {import('next').NextConfig} */
const nextConfig = {
	async redirects() {
		return [
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
