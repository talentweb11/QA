/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      }
    }
  },
  test: {
    globals: true,             // use describe/it/expect without importing them
    environment: 'jsdom',      // simulate a browser DOM for React components
    setupFiles: './src/test/setup.ts',
  },
})
