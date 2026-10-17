/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  transpilePackages: ['react-force-graph-2d', 'force-graph', 'd3-force'],
};

module.exports = nextConfig;
