import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'url';
import path from 'path';
import reactAgentBridgeBabelPlugin from '../../../dist/babel-plugin.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [reactAgentBridgeBabelPlugin],
      },
    }),
  ],
  resolve: {
    alias: {
      'react-agent-bridge': path.resolve(__dirname, '../../../dist/index.js'),
    },
  },
});
