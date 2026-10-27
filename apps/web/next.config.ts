import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Keep development and production artifacts separate so an IDE build cannot
  // invalidate a running Turbopack dev server.
  distDir: process.env.SPANTRACE_NEXT_DIST_DIR || (process.env.NODE_ENV === "development" ? ".next-dev" : ".next-build"),
};

export default nextConfig;
