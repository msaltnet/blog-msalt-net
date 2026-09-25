import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { site, categoryOrder } from '../data/site';

export const GET: APIRoute = async () => {
  const posts = await getCollection('posts', ({ data }) => !data.draft);
  const tags = [...new Set(posts.flatMap((post) => post.data.tags))];
  const urls = [
    `<url><loc>${site.url}/</loc></url>`,
    ...categoryOrder.map((category) => `<url><loc>${site.url}/category/${encodeURIComponent(category)}</loc></url>`),
    ...tags.map((tag) => `<url><loc>${site.url}/tag/${encodeURIComponent(tag)}</loc></url>`),
    ...posts.map(({ data }) => `<url><loc>${site.url}/${data.id}</loc><lastmod>${data.date.toISOString()}</lastmod></url>`),
  ];
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join('')}</urlset>`, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
