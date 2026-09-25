import process from 'node:process';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ command, mode }) => {
  if (command === 'build' && process.env.VERCEL === '1') {
    const base = loadEnv(mode, process.cwd()).VITE_API_BASE_URL;
    if (!base || !base.startsWith('https://')) {
      throw new Error('Impostare VITE_API_BASE_URL con il dominio HTTPS del backend Railway.');
    }
  }
  return {
    plugins: [react()],
    test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], clearMocks: true },
  };
});
