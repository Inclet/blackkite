import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

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
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
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
