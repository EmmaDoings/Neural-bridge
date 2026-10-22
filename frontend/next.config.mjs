import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The repository root also has a lockfile (for tooling), which makes
  // Turbopack guess the wrong workspace root. Pin it to the frontend so only
  // this app's files are watched and resolved.
  turbopack: {
    root: currentDirectory
  }
};

export default nextConfig;
