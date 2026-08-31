import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxies API calls to the FastAPI backend (see docker-compose.yml) so the
    // frontend can use relative fetch URLs without needing CORS configured.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
