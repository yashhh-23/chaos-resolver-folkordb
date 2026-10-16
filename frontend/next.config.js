/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  transpilePackages: ['react-force-graph-2d', 'force-graph', 'd3-force'],
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://orgbridge-ai-backend.onrender.com',
  },
};

module.exports = nextConfig;
