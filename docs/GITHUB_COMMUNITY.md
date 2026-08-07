# GitHub community surfaces (Wiki · Pages · Discussions)

In-repo content is complete under `docs/wiki/`, `docs/index.html`, and `docs/discussions/`.  
Publishing Wiki/Discussions/Pages may require **one-time** toggles in GitHub Settings if the token lacks `admin:repo`.

## 1. Enable features (repo owner UI)

GitHub → **Qoresence** → **Settings**:

| Feature | Path | Action |
|---------|------|--------|
| **Wiki** | Features | Enable Wikis |
| **Discussions** | Features | Enable Discussions |
| **Pages** | Pages | Source: **Deploy from a branch** → Branch `main` → Folder `/docs` → Save |

Or after pushing, run (needs admin-capable token):

```powershell
gh repo edit ConWan30/Qoresence --enable-wiki --enable-discussions --homepage "https://conwan30.github.io/Qoresence/"
```

## 2. Publish Wiki from `docs/wiki/`

```powershell
# From repo root after Wiki is enabled
.\scripts\publish_wiki.ps1
```

This clones `Qoresence.wiki.git`, copies `docs/wiki/*.md`, commits, and pushes.

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
