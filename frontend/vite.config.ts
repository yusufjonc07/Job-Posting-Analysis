import type { ServerResponse } from 'node:http'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { createLogger, defineConfig } from 'vite'

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

// Collapse the stack trace Vite prints for every proxied request while the backend is down.
const logger = createLogger()
const logError = logger.error.bind(logger)
let lastOfflineLog = 0
logger.error = (msg, options) => {
  if (msg.includes('proxy error') && /ECONNREFUSED|ECONNRESET|socket hang up/.test(msg)) {
    const now = Date.now()
    if (now - lastOfflineLog > 10_000) {
      lastOfflineLog = now
      logger.warn(`[api] backend unreachable at ${apiTarget} (start it with: .venv/bin/uvicorn src.api.main:app)`, {
        timestamp: true,
      })
    }
    return
  }
  logError(msg, options)
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  customLogger: logger,
  cacheDir: process.env.VITE_CACHE_DIR ?? 'node_modules/.vite',
  build: {
    rolldownOptions: {
      output: {
        // Libraries in their own long-cacheable files; each page is loaded on demand (React.lazy in App.tsx).
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/, priority: 30 },
            { name: 'charts', test: /node_modules[\\/](recharts|d3-[^\\/]+|victory-vendor|internmap|es-toolkit|decimal\.js-light|immer|reselect|redux|@reduxjs|react-redux|use-sync-external-store|eventemitter3|tiny-invariant|react-is)[\\/]/, priority: 20 },
            { name: 'vendor', test: /node_modules/, priority: 10 },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq, req) => {
            // SSE must stream unbuffered and uncompressed through the proxy.
            if (req.url?.startsWith('/api/events')) proxyReq.setHeader('accept-encoding', 'identity')
          })
          proxy.on('proxyRes', (proxyRes, req, res) => {
            if (req.url?.startsWith('/api/events')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
              proxyRes.headers['x-accel-buffering'] = 'no'
              ;(res as ServerResponse).flushHeaders?.()
            }
          })
          proxy.on('error', (_err, _req, res) => {
            // Answer with a JSON 502 the client recognises as "backend offline".
            const out = res as ServerResponse
            if ('writeHead' in out && !out.headersSent && !out.writableEnded) {
              out.writeHead(502, { 'Content-Type': 'application/json' })
              out.end(JSON.stringify({ detail: 'Backend unreachable', offline: true }))
            }
          })
        },
      },
    },
  },
  preview: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
})
