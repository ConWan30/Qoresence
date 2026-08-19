# GitHub community surfaces (Wiki · Pages · Discussions)

In-repo content is complete under `docs/wiki/`, `docs/index.html`, and `docs/discussions/`.  
Publishing Wiki/Discussions/Pages may require **one-time** toggles in GitHub Settings if the token lacks `admin:repo`.

## 1. Enable features (repo owner UI) — **required once**

The automation PAT cannot flip Features (HTTP 403). As **repo owner**, open:

**https://github.com/ConWan30/Qoresence/settings**

| Feature | Path | Action |
|---------|------|--------|
| **Wiki** | General → Features | ☑ Wikis |
| **Discussions** | General → Features | ☑ Discussions |
| **Pages** | Pages | Build and deployment → Source: **GitHub Actions** |

Then re-run publish scripts / re-run the **Deploy GitHub Pages** workflow.

Or with an admin-scoped token:

```powershell
gh repo edit ConWan30/Qoresence --enable-wiki --enable-discussions --homepage "https://conwan30.github.io/Qoresence/"
```

## 2. Publish Wiki from `docs/wiki/`

```powershell
# From repo root after Wiki is enabled
.\scripts\publish_wiki.ps1
```

This clones `Qoresence.wiki.git`, copies `docs/wiki/*.md`, commits, and pushes.

## Existing milestone discussions

- [Discussion #21 — Qoresence: OpenTelemetry causal tracing for DualSense → capture card gameplay clips](https://github.com/ConWan30/Qoresence/discussions/21)

## 3. Publish Discussions

After Discussions are enabled:

```powershell
.\scripts\publish_discussions.ps1
```

Creates Announcements from `docs/discussions/*.md` via GraphQL.

## 4. Pages

With Pages source = `main` / `/docs`, the site is:

**https://conwan30.github.io/Qoresence/**

Landing file: `docs/index.html`.

## 5. Topics (optional)

```powershell
gh repo edit ConWan30/Qoresence --add-topic streamer,obs,dualsense,twitch,local-first,game-capture,python
```
