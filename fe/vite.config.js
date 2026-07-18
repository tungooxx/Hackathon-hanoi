import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget =
  process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/chat': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/health': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
