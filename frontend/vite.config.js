import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    strictPort: true,
    // Proxies API calls to the FastAPI backend (see docker-compose.yml) so the
    // frontend can use relative fetch URLs without needing CORS configured.
    // FastAPI routes are unprefixed (e.g. /cases), so strip /api before forwarding.
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
