import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/chat': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
          timeout: 300000,
          proxyTimeout: 300000,
        },
        '/feedback': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '/analyze_image': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        }
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
