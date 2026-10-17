const { API_BASE } = require("./lib/config.ts");

const nextConfig = {
  reactStrictMode: false,
  transpilePackages: ['react-force-graph-2d', 'force-graph', 'd3-force'],
  env: {
    NEXT_PUBLIC_API_URL: API_BASE,
  },
};

module.exports = nextConfig;
