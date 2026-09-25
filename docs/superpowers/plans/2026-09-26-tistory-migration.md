# Tistory Blog Migration Implementation Plan

> **For agentic workers:** Execute this plan inline, one milestone at a time. Do not perform DNS changes or publish a production cutover.

**Goal:** Build an Astro static site and repeatable migration pipeline for `https://blog.msalt.net/` while preserving content and legacy URLs.

**Architecture:** Use an Astro content collection for Markdown posts, static local assets, and an ID-based route for legacy post paths. Keep inventory, transformation, and validation in separate scripts; retain source HTML and media backups as the recovery copy.

**Tech Stack:** Astro, Markdown, Python migration scripts, GitHub repository `msaltnet/blog-msalt-net`; hosting is selected after URL inventory.

**Spec:** `docs/superpowers/specs/2026-09-26-tistory-to-astro-design.md`

## Global Constraints

- Preserve actual existing IDs and URLs; never synthesize IDs.
- Back up source HTML and media before transforming content.
- Keep complex HTML when converting it would lose information.
- Do not choose production hosting until inventory and redirect needs are known.
- Do not change DNS, delete Tistory, publish a cutover, or add AdSense.
- Do not save secrets, cookies, or credentials.

---

## Milestone 1: Inventory and source backup

**Files:**
- Create: `scripts/inventory.py`
- Create: `scripts/backup.py`
- Create: `migration/README.md`
- Generate: `migration/posts.csv`, `migration/categories.csv`, `migration/tags.csv`, `migration/images.csv`, `migration/urls.csv`
- Generate: `backup/html/<post-id>.html`, `backup/images/<post-id>/`, `backup/metadata/posts.json`

1. Inspect the current site HTML, pagination, categories, tags, and post pages to identify stable selectors and request behavior.
2. Implement a crawler that follows pagination and records every post's ID, canonical URL, title, date, category, tags, and source page URL.
3. Record non-post URL patterns including category, tag, search, RSS, mobile, and pagination routes.
4. Download each post's original HTML and referenced image assets into the backup layout, preserving captions and source URLs in metadata.
5. Write CSV/JSON outputs with deterministic ordering and explicit per-URL errors; do not silently skip failed pages or assets.
6. Review inventory totals, duplicates, failed URLs, and media errors against the public site before accepting the source snapshot.

**Completion evidence:** an inventory with a count reconciled against the public site, HTML available for every inventoried post, and a report listing any inaccessible pages or assets.

## Milestone 2: Astro foundation and design recreation

**Files:**
- Create: `package.json`, lockfile, `astro.config.mjs`, `src/content.config.ts`
- Create: `src/content/posts/`, `src/layouts/BaseLayout.astro`, `src/layouts/PostLayout.astro`
- Create: `src/components/Header.astro`, `Sidebar.astro`, `PostList.astro`, `PostMeta.astro`, `Footer.astro`
- Create: `src/pages/index.astro`, `src/pages/[id].astro`, `src/pages/category/[...category].astro`

1. Initialize the Astro project and define a validated posts collection using the approved frontmatter fields.
2. Build shared layout and components around the current public site's structure and visual styling.
3. Generate a static route for every post ID and preserve the trailing-slash behavior observed in the inventory.
4. Add category routes based on actual category names and generate links from post metadata.
5. Remove Tistory-specific toolbar, login, advertising, and comment scripts from the new site.

**Completion evidence:** the homepage, one representative post, and category pages render from local fixture content at their intended paths.

## Milestone 3: Content and asset migration

**Files:**
- Create: `scripts/migrate.py`
- Create: `src/content/posts/<post-id>.md`
- Create: `public/images/posts/<post-id>/`

1. Parse the saved HTML and metadata backups without making the live site a dependency of conversion.
2. Extract title, date, category, tags, description, original URL, cover image, and comments when available.
3. Convert supported HTML to Markdown and preserve unsupported structures as raw HTML.
4. Copy images and attachments into the local asset tree and rewrite references to local paths.
5. Produce a conversion report with source count, output count, missing metadata, remote asset references, and parse errors.

**Completion evidence:** every inventoried post has a generated content file, and every image reference resolves to a local backup or is listed as an error.

## Milestone 4: Compatibility and feeds

**Files:**
- Create: `src/pages/rss.xml.ts`, `public/robots.txt`
- Create: `src/pages/sitemap-index.xml.ts` or Astro sitemap integration configuration
- Create: redirect configuration only after hosting is selected
- Modify: base and post layouts for canonical, Open Graph, Twitter Card, and Article JSON-LD

1. Preserve `/rss` and generate valid RSS entries from migrated posts.
2. Emit self-referencing canonical URLs using `https://blog.msalt.net`.
3. Generate sitemap and robots.txt from the final route inventory.
4. Compare inventoried legacy URL types against generated routes and create redirects only for paths that cannot be reproduced.
5. Select GitHub Pages or Cloudflare Pages based on the measured redirect requirements.

**Completion evidence:** every retained or redirected legacy URL has a documented destination, and generated SEO/feed files reference the production canonical domain.

## Milestone 5: Verification and preview

**Files:**
- Create: `scripts/verify.py`
- Create: `migration/review-samples.csv`

1. Verify that every inventoried post has an output route and canonical URL.
2. Check local image references, internal links, RSS XML, sitemap entries, and remaining Tistory CDN/script references.
3. Compare representative newest, oldest, image-heavy, table, video, long-form, and comment-bearing posts with their backups.
4. Deploy a preview environment and inspect desktop and mobile layouts.
5. Fix migration errors and rerun the complete verification report.

**Completion evidence:** all automated checks pass, sample review issues are resolved or documented, and preview review is complete. Production DNS remains unchanged.

## Milestone 6: Cutover preparation (separate approval required)

1. Pause new Tistory publishing and take a final inventory/backup snapshot.
2. Re-run conversion and verification against the final snapshot.
3. Register the domain with the chosen host, confirm HTTPS, and document rollback settings.
4. Present a cutover checklist for explicit approval before any DNS change.
