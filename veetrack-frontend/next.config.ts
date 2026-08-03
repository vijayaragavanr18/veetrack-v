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
    minimumCacheTTL: 3600,
    // Allow local SVG placeholders in public/story-images/
    dangerouslyAllowSVG: true,
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
        pathname: "/**",
      },
      {
        protocol: "http",
        hostname: "**",
        pathname: "/**",
      },
    ],
  },

  experimental: {
    // Tree-shake lucide-react — only import the icons actually used.
    // Without this, the full 1 500-icon bundle is included.
    optimizePackageImports: ["lucide-react", "@radix-ui/react-icons"],
  },
};

export default withBundleAnalyzer(nextConfig);
