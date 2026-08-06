import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["10.0.0.45"],
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
