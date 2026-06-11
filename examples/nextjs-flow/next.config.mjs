import { createRequire } from 'module';
const require = createRequire(import.meta.url);

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required to allow Babel to run alongside Next.js.
  // Without this, Next.js uses SWC exclusively and the Babel plugin cannot be applied.
  experimental: {
    forceSwcTransforms: false,
  },
  babel: {
    plugins: [require.resolve('react-agent-bridge/babel-plugin')],
  },
};

export default nextConfig;
