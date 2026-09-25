import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://blog.msalt.net',
  trailingSlash: 'never',
  build: { format: 'file' },
});
