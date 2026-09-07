/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backendTarget = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000';

// Im Entwicklungsbetrieb laeuft alles ueber einen Ursprung, dadurch entfallen
// CORS-Sonderfaelle im Browser. Im Container uebernimmt nginx diese Rolle.
const apiProxy = { '/api': { target: backendTarget, changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, proxy: apiProxy },
  preview: { host: true, port: 4173, proxy: apiProxy },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
