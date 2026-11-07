import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');

  return {
    plugins: [react()],
    server: {
      watch: {
        ignored: [
          '**/artifacts/**',
          '**/test-results/**',
          '**/playwright-report/**',
        ],
      },
      proxy: {
        '/api': env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test-setup.ts',
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
