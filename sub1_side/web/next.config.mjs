/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const api = process.env.C2_PROXY_API || "http://127.0.0.1:8000";
    return [
      { source: "/c2/:path*", destination: `${api}/c2/:path*` },
      { source: "/robots/:path*", destination: `${api}/robots/:path*` },
      { source: "/telemetry/:path*", destination: `${api}/telemetry/:path*` },
      { source: "/healthz", destination: `${api}/healthz` },
    ];
  },
};
export default nextConfig;
