/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // Not VITE_-prefixed, so it stays out of the browser bundle.
  const { API_PROXY_TARGET = 'http://localhost:8000' } = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      // In production the static site and API share an origin; mirror that locally.
      proxy: {
        '/api': API_PROXY_TARGET,
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
