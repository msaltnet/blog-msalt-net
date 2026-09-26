import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const outputDirectory = fileURLToPath(new URL('../docs/', import.meta.url));
const base = process.env.SITE_BASE ?? '/blog-msalt-net';
const prefix = base === '/' ? '' : `/${base.replace(/^\/+|\/+$/g, '')}`;

async function processDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await processDirectory(path);
    } else if (entry.isFile() && entry.name.endsWith('.html')) {
      const html = await readFile(path, 'utf8');
      const updated = html.replace(/((?:src|href)=["'])\/images\//g, `$1${prefix}/images/`);
      if (updated !== html) await writeFile(path, updated);
    }
  }
}

await processDirectory(outputDirectory);
