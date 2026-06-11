import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import reactAgentBridgeBabelPlugin from 'react-agent-bridge/babel-plugin';

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [reactAgentBridgeBabelPlugin],
      },
    }),
  ],
});
