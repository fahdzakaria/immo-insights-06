import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone", // image Docker légère (Phase 7 : déploiement)
};

export default nextConfig;
