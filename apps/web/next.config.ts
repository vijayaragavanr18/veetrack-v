import type { NextConfig } from "next";

const withBundleAnalyzer =
  process.env.ANALYZE === "true"
    ? // eslint-disable-next-line @typescript-eslint/no-require-imports
      require("@next/bundle-analyzer")({ enabled: true })
    : (config: NextConfig) => config;

const nextConfig: NextConfig = {
  compress: true,
  // Required for Docker standalone output (copies server.js + minimal deps).
  output: "standalone",

  images: {
    // Serve hero images in modern formats for smaller payloads.
    formats: ["image/avif", "image/webp"],
    // Cache optimised images in CDN/browser for 1 hour (3600 s).
    // Hero images don't change once ingested so a 1 h TTL is conservative.
    minimumCacheTTL: 3600,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "picsum.photos",
        pathname: "/**",
      },
      // MinIO/S3 hero image cache — add your bucket hostname here when live.
      // { protocol: "https", hostname: "media.veetrack.io", pathname: "/heroes/**" },
    ],
  },

  experimental: {
    // Tree-shake lucide-react — only import the icons actually used.
    // Without this, the full 1 500-icon bundle is included.
    optimizePackageImports: ["lucide-react", "@radix-ui/react-icons"],
  },
};

export default withBundleAnalyzer(nextConfig);
