import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    id: z.string(),
    title: z.string(),
    date: z.coerce.date(),
    category: z.string(),
    tags: z.array(z.string()).default([]),
    description: z.string().default(''),
    legacyUrl: z.string(),
    originalUrl: z.string().url().optional().or(z.literal('')),
    coverImage: z.string().default(''),
    draft: z.boolean().default(false),
  }),
});

export const collections = { posts };
