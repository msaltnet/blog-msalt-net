# Migration inventory and backups

Run the inventory from the `blog-msalt-net` project directory:

```powershell
python scripts/inventory.py
python scripts/backup.py
```

`inventory.py` follows public homepage, category, tag, archive, search, and pagination links on the configured site, then fetches metadata for every discovered numeric post permalink. Results are written to `migration/`. The first crawl is exploratory: inspect `errors.json`, compare the post total with the live site's displayed total, and review unusual URL patterns before treating the inventory as complete.

`backup.py` uses `migration/posts.csv` to save each post's original HTML under `backup/html/` and referenced images under `backup/images/<post-id>/`. Source images are recorded with alt text, title, caption, and original URL when available. Comments are intentionally excluded from the migration.

The public site can change during collection. Keep each inventory and backup snapshot together and rerun both commands for the final snapshot before any cutover. The scripts do not change the live site or DNS.

After the source snapshot has been reviewed, convert it and check the output:

```powershell
python scripts/migrate.py
python scripts/verify.py
```

The first collected snapshot contains 320 accessible posts. The homepage reports 321, and one category's displayed total differs from the links returned by its public listing. These discrepancies are reported for later source review rather than guessed or synthesized.
