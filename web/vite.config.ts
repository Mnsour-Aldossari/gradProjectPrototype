import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards API and WebSocket calls to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
