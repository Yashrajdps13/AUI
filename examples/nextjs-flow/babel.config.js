module.exports = {
  presets: [
    // Next.js requires next/babel as the base preset
    'next/babel',
  ],
  plugins: [
    // react-agent-bridge Babel plugin — instruments Client Component
    // useState calls to register them in the bridge registry.
    // Files without 'use client' are automatically skipped.
    'react-agent-bridge/babel-plugin',
  ],
};
