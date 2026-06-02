import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    setupFiles: ['./src/setup-tests.ts'],
    server: {
      deps: {
        inline: [
          '@csstools/css-calc',
          '@asamuzakjp/css-color',
        ],
      },
    },
  },
});
