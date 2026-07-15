# Deploying eob-site-scripts.js

The EOB equivalent of Ambitious Harvest's `ah-site-scripts.js`. It runs only on article pages (`/library/<slug>`) and injects: **branded in-article graphics** (18 built: comparison tables, stat cards, step timelines, checklists, note boxes, anchored to real article headings, all data pulled from the articles' own sourced text), a **"Keep Reading"** related-articles row, light **FAQ** styling, and (once affiliate links are live) a keyword-routed **recommendation callout**. It never touches data, only injects UI.

## One-time deploy (about 2 minutes)

1. **Publish the file to the CDN.** It lives at the repo root; commit and push:
   ```
   cd "Website/execops-brief-assets"
   git add eob-site-scripts.js DEPLOY_site-scripts.md
   git commit -m "Add site-wide behavior layer"
   git push
   ```
   It is then served at:
   `https://cdn.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/eob-site-scripts.js`

2. **Load it from Squarespace.** Settings > Advanced > Code Injection > HEADER, add ONE line at the end of the existing injection (do NOT replace what is there, the live header is the v2 design system):
   ```html
   <script defer src="https://cdn.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/eob-site-scripts.js"></script>
   ```

3. **Smoke-test.** Open any published `/library/<slug>` article. You should see a "Keep Reading" row at the end with three related cards. If nothing appears, the blog template uses a different content container: open the browser console and adjust `contentEl()`'s selector list in the file, then push + purge (step below).

## After any edit
```
git commit -am "..." && git push
curl -s "https://purge.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/eob-site-scripts.js"
```
The jsDelivr purge makes the change live within a minute or two.

## Keeping it current
- **New articles:** add a `{s,t,p}` row to the `ARTICLES` array (slug, title, pillar).
- **In-article graphics:** add entries to the `GRAPHICS` array. Each is `{ slug, after, type, data }` where `after` is a substring of a real heading in that article and `type` is one of note / stat / table / steps / checklist. A graphic whose `after` heading is not found is skipped, so it is safe to leave entries for not-yet-published articles.
- **Affiliate callouts:** paste the copy from `Commercialization/Affiliate_Program_Plan.md` into the `CALLOUTS` array. The module stays dormant while that array is empty, so it is safe to ship before any affiliate program is joined.
