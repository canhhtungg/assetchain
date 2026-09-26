import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: '/assetchain/',
  plugins: [
    react(),
    command === 'build' && {
      name: 'assetchain-production-csp',
      transformIndexHtml() {
        return {
          tags: [
            {
              tag: 'meta',
              attrs: {
                'http-equiv': 'Content-Security-Policy',
                content: "default-src 'self'; connect-src 'self' https://ubuntu-fabric.tail3949da.ts.net; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'none'; worker-src 'none'",
              },
              injectTo: 'head-prepend',
            },
          ],
        }
      },
    },
  ].filter(Boolean),
}))
