import type { NextConfig } from 'next';
const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // Self-contained server for the container image (deploy/Containerfile.frontend).
  output: 'standalone',
  env: {
    NEXT_PUBLIC_WORKSPACE_TIME_ZONE: process.env.TANTARA_WORKSPACE_TIME_ZONE ?? 'Asia/Kolkata',
  },
  async rewrites() {
    const origin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
    return [
      { source: '/api/v1/ingest/file', destination: `${origin}/ingest/file` },
      { source: '/api/v1/:path*', destination: `${origin}/api/v1/:path*` },
      { source: '/health', destination: `${origin}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, s-maxage=60, must-revalidate',
          },
        ],
      },
      {
        source: '/_next/static/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ];
  },
};
export default nextConfig;
