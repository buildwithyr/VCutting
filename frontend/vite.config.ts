/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backendTarget = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Im Entwicklungsbetrieb laeuft alles ueber einen Ursprung, dadurch
    // entfallen CORS-Sonderfaelle im Browser.
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
    },
  },
  preview: { host: true, port: 4173 },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
