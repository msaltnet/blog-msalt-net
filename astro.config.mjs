import { defineConfig } from 'astro/config';

const base = process.env.SITE_BASE ?? '/';

export default defineConfig({
  site: 'https://blog.msalt.net',
  base,
  trailingSlash: 'never',
  outDir: './docs',
  build: { format: 'file' },
});
