import { getCollection } from 'astro:content';

export async function GET() {
  const posts = await getCollection('posts', ({ data }) => !data.draft);
  const index = posts.map(({ data, body }) => ({
    id: data.id,
    title: data.title,
    category: data.category,
    date: data.date.toISOString(),
    url: data.legacyUrl,
    description: data.description,
    body: body ?? '',
  }));

  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
