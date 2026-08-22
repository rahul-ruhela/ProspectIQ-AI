import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { devStackPlugin } from './devstack.plugin'

export default defineConfig({
  // devStackPlugin is `apply: 'serve'`, so it exists in `npm run dev` only and is
  // never part of a production bundle.
  plugins: [react(), devStackPlugin()],
  server: {
    port: 5173,
    host: true,
  },
  preview: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Charts and the router change far less often than app code; splitting them
        // keeps the app chunk small and cacheable across deploys.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          data: ['@tanstack/react-query', 'axios', 'zustand'],
        },
      },
    },
  },
})
