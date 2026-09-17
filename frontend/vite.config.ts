import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Native fs.watch doesn't reliably fire for files on a Windows-mounted
    // drive under WSL2 (e.g. this project living under /mnt/d) — edits were
    // silently not triggering HMR, discovered when a just-fixed bug kept
    // reproducing because the browser was still running the pre-fix bundle.
    // Polling is slower but actually detects changes here.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
