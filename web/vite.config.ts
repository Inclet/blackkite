import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { apiProxy } from './apiProxy.ts';
import { referrerPolicyFor, workboxOptions } from './pwa.ts';

const designDir = fileURLToPath(new URL('../design', import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      // The approved design lives outside the web app; import it, never copy it.
      '@design': designDir,
    },
  },
  server: {
    fs: { allow: ['.', designDir] },
    proxy: apiProxy(),
  },
  preview: {
    proxy: apiProxy(),
  },
  plugins: [
    react(),
    {
      // The preview server sends Referrer-Policy as the edge server does, so e2e can tell
      // a network response from the service worker's cached index.html.
      name: 'bk-preview-referrer-policy',
      configurePreviewServer(server) {
        server.middlewares.use((req, res, next) => {
          res.setHeader('Referrer-Policy', referrerPolicyFor(new URL(req.url ?? '/', 'http://x').pathname));
          next();
        });
      },
    },
    VitePWA({
      registerType: 'autoUpdate',
      workbox: workboxOptions,
      includeAssets: ['fonts/*.woff2', 'fonts/google-figtree.css'],
      manifest: {
        name: 'Blackkite',
        short_name: 'Blackkite',
        theme_color: '#2B2A28',
        background_color: '#F6F5F2',
        display: 'standalone',
        start_url: '/',
        // TODO(design): placeholder icons (flat #2B2A28 squares). Replace with the
        // kite mark once app icons are designed: icons/icon-192.png, icons/icon-512.png,
        // icons/icon-maskable-512.png.
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
});
