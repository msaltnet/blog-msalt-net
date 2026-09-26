import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://blog.msalt.net',
  trailingSlash: 'never',
  outDir: './docs',
  build: { format: 'file' },
});
