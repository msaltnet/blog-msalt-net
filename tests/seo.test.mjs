import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const output = new URL('../docs/', import.meta.url);
const readPage = (path) => readFile(new URL(path, output), 'utf8');
const meta = (html, attribute, value) => {
  const tags = html.match(/<meta\s+[^>]*>/g) ?? [];
  return tags.find((tag) => tag.includes(`${attribute}="${value}"`)) ?? '';
};

test('homepage has site metadata and a usable share image', async () => {
  const html = await readPage('index.html');
  assert.match(meta(html, 'name', 'description'), /개발/);
  assert.match(meta(html, 'property', 'og:type'), /content="website"/);
  assert.match(meta(html, 'property', 'og:image'), /https:\/\/blog\.msalt\.net\/images\/sidebar\/blog-image\.jpg/);
  assert.match(meta(html, 'name', 'twitter:image'), /https:\/\/blog\.msalt\.net\//);
  assert.doesNotMatch(html, /"@type":"BlogPosting"/);
});

test('posts have concise descriptions and article identity', async () => {
  const html = await readPage('101.html');
  const description = meta(html, 'name', 'description');
  assert.ok(description.length < 250, `description tag is ${description.length} characters`);
  assert.match(meta(html, 'property', 'og:type'), /content="article"/);
  assert.match(meta(html, 'property', 'article:published_time'), /2015-08-18/);
  assert.match(meta(html, 'property', 'og:image:alt'), /content=/);
  assert.match(html, /"@type":"BlogPosting"/);
  assert.match(html, /"author":\{"@type":"Person"/);
});

test('posts without a cover image use the default share image', async () => {
  const html = await readPage('1.html');
  assert.match(meta(html, 'property', 'og:image'), /blog-image\.jpg/);
  assert.match(meta(html, 'name', 'twitter:card'), /summary_large_image/);
});

test('search results are excluded from indexing', async () => {
  const html = await readPage('search.html');
  assert.match(meta(html, 'name', 'robots'), /noindex/);
});
