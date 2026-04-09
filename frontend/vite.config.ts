import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const backendTarget = (env: Record<string, string>) =>
  env.VITE_API_URL || 'http://127.0.0.1:8000';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const target = backendTarget(env);
  return {
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        // SSE streaming endpoint — must NOT buffer the response
        '/chat': {
          target,
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('proxyReq', (_proxyReq, req) => {
              // Force HTTP/1.1 keep-alive so SSE chunks aren't buffered
              req.socket.setKeepAlive(true);
            });
          },
        },
        '/feedback': {
          target,
          changeOrigin: true,
          secure: false,
        },
        '/analyze_image': {
          target,
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target,
          changeOrigin: true,
          secure: false,
        },
        '/status': {
          target,
          changeOrigin: true,
          secure: false,
        },
      }
    },
    plugins: [react()],
    define: {
      'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    }
  };
});
