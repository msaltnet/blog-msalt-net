# Tistory to Astro Migration Design

## Goal

Migrate `https://blog.msalt.net/` from Tistory to an Astro static site while preserving post content, existing post URLs, and the current site's information architecture as closely as possible.

## Constraints

- Treat the public Tistory site as the source of truth for the complete post and URL inventory.
- Never infer missing post IDs from a numeric sequence.
- Preserve original HTML and downloaded media separately from converted Markdown.
- Keep Tistory and existing DNS configuration available until preview and migration verification are complete.
- Do not choose a hosting provider until the URL inventory establishes whether redirects are needed.
- Do not perform DNS changes or remove the Tistory source as part of implementation.
- Do not store credentials, cookies, or other secrets in the repository.

## Architecture

The site will use Astro static generation. Markdown files in an Astro content collection will hold migrated posts with stable Tistory IDs in frontmatter. A dynamic route will emit `/[id]/` pages so legacy post paths can remain stable. Static assets will be stored locally under `public/images/posts/<id>/`; complex HTML fragments may remain HTML inside Markdown to avoid content loss.

Migration tooling will be divided by responsibility:

- `scripts/inventory.py` discovers existing posts and URL types and writes machine-readable inventory files.
- `scripts/migrate.py` consumes saved source backups and produces Markdown, frontmatter, and local assets.
- `scripts/verify.py` checks route coverage, assets, internal links, canonical URLs, RSS, sitemap, and remaining Tistory dependencies.

The initial implementation milestone is inventory and source backup. Site rendering and full content conversion follow from the observed source structure.

## Content and routes

The minimum post metadata is `id`, `title`, `date`, `category`, `tags`, `description`, `legacyUrl`, `coverImage`, and `draft`; `updated` and `originalUrl` may be included when present. Existing post IDs and paths are preserved. Category, tag, pagination, mobile, search, and feed URLs are inventoried before deciding which can be reproduced directly and which require redirects.

The migrated site will include self-referencing canonical URLs, Open Graph and Twitter metadata, Article JSON-LD, sitemap, robots.txt, and an RSS endpoint matching `/rss` where feasible. Existing comments are preserved as static data when available; a new comment service is outside the migration baseline.

## Design and operations

Recreate the current site's header, post body, metadata, category navigation, sidebar, and footer before any redesign. Remove Tistory-only scripts, toolbar, login, and advertising code. Deploy to a preview host before selecting final hosting. GitHub Pages is sufficient if routes can be preserved directly; Cloudflare Pages is preferred if many redirect rules are needed.

## Verification and completion

The migration is ready for preview review when all inventoried posts have source backups, all source media is either archived or explicitly reported as unavailable, generated post routes cover the inventory, internal links and assets resolve, canonical URLs are correct, the sitemap and RSS are valid, and no Tistory runtime/CDN dependency remains in migrated content. Representative posts with images, tables, video embeds, long text, and comments receive manual comparison.

DNS cutover, Search Console/analytics follow-up, and AdSense setup are later operational steps and are not performed during implementation without a separate explicit request.
