/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  transpilePackages: ['react-force-graph-2d', 'force-graph', 'd3-force'],
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      (process.env.NODE_ENV === "development"
        ? "http://localhost:8000"
        : "https://orgbridge-ai-backend.onrender.com"),
  },
};

module.exports = nextConfig;
