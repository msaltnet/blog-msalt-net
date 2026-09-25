import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { site } from '../data/site';

const escapeXml = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');

export const GET: APIRoute = async () => {
  const posts = (await getCollection('posts', ({ data }) => !data.draft)).sort((a,b) => b.data.date.valueOf() - a.data.date.valueOf()).slice(0, 50);
  const items = posts.map(({ data }) => `
    <item><title>${escapeXml(data.title)}</title><link>${site.url}/${data.id}</link><guid isPermaLink="true">${site.url}/${data.id}</guid><pubDate>${data.date.toUTCString()}</pubDate><category>${escapeXml(data.category)}</category><description>${escapeXml(data.description)}</description></item>`).join('');
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>${escapeXml(site.title)}</title><link>${site.url}</link><description>${escapeXml(site.description)}</description><language>ko-KR</language>${items}</channel></rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
};
