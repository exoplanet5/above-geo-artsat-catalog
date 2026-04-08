# Deploying the Above-GEO Artsat Catalog

The catalog is a static site (HTML + JS + CSS + one JSON file). The data
file is built locally from `~/tles/tle_list.txt`; the rest is plain
frontend code that can be served from any static host.

The **default deployment path** is:

> `local make build` → `git push` to GitHub → **GitHub Action automatically
> rebuilds and uploads the static bundle to your Hugging Face Space.**

You only push to GitHub. The HF Space stays in sync on its own.

```
   ┌────────────────┐    git push    ┌──────────────┐    upload_folder()    ┌──────────────────┐
   │  local laptop  │ ─────────────► │   GitHub     │ ─────────────────────►│  HF Static Space │
   │  make build    │                │  + Action    │                        │  (auto-rebuild)  │
   └────────────────┘                └──────────────┘                        └──────────────────┘
```

The manual `git push` to the HF remote remains available as a fallback at
the bottom of this doc, but you should not need it for routine updates.

---

## 0. One-time prerequisites

- A GitHub account
- A Hugging Face account: <https://huggingface.co/join>
- `git`, `make`, and the local Python env you already use for `build.py`
  (`~/.venvs/astro313/bin/python`)

---

## 1. Create the GitHub repo

This walkthrough assumes the `catalog/` directory itself becomes the
**root** of a dedicated GitHub repo. If you would rather host it as a
subdirectory of a monorepo, see the *Monorepo layout* note at the bottom.

```bash
cd /Users/mickey/ciscluar/highartsat/catalog

git init -b main
git add .
git commit -m "Initial above-GEO artsat catalog"

# Create the empty repo on github.com first (or with the gh CLI), then:
git remote add origin git@github.com:YOUR_GH_USER/above-geo-artsat-catalog.git
git push -u origin main
```

`.gitignore` already excludes `dist/` and `__pycache__/`. The committed
files include the source frontend, `build.py`, the HF Space template
(`deploy/README.md`), the Makefile, the workflow, and the most recent
`data/orbits.json` snapshot.

> **Why commit `data/orbits.json`?** CI runners do not have your local
> `~/tles` files, so they cannot run `build.py`. Committing the JSON
> snapshot lets CI assemble `dist/` directly without needing TLE access,
> and it gives you a reproducible record of which TLE epoch each release
> was built from. The file is ~370 KB, well within plain-git limits.

---

## 2. Create the Hugging Face Space

1. <https://huggingface.co/new-space>
2. **Owner**: your HF username (or an org)
3. **Space name**: e.g. `above-geo-artsat-catalog`
4. **License**: whatever fits (MIT is fine for a viewer over public TLE data)
5. **SDK**: choose **Static**
6. **Visibility**: Public (or Private if you prefer)
7. Click **Create Space**

The new Space starts as an empty repo with a placeholder `README.md`. The
GitHub Action will overwrite it on the first sync; you do not need to
upload anything by hand.

Note the full Space repo id, e.g.:

```
yourname/above-geo-artsat-catalog
```

---

## 3. Wire up the GitHub Action

The workflow at `.github/workflows/sync-hf.yml` needs two pieces of repo
configuration. Both live under the GitHub repo's
**Settings → Secrets and variables → Actions**.

### 3a. Add the HF access token (secret)

1. On HF, go to <https://huggingface.co/settings/tokens>
2. Click **New token**, give it a name like `gh-action-sync`, set the
   role to **write**, and create it.
3. Copy the token (it is only shown once).
4. In your GitHub repo: **Settings → Secrets and variables → Actions →
   Secrets → New repository secret**
   - Name: `HF_TOKEN`
   - Value: paste the token

### 3b. Add the target Space repo id (variable)

In the same screen, switch to the **Variables** tab and add:

- Name: `HF_REPO_ID`
- Value: `yourname/above-geo-artsat-catalog` (the full Space repo id)

A variable (not a secret) is fine here because the value is already
public on the HF Space page.

---

## 4. Trigger the first sync

You have two options to fire the workflow.

**Option A — push something:**

```bash
git commit --allow-empty -m "Trigger HF sync"
git push
```

**Option B — manual dispatch from the Actions tab:**

1. GitHub repo → **Actions** tab
2. Pick **Sync to Hugging Face Space** in the sidebar
3. Click **Run workflow** → **Run workflow** (on `main`)

Either way, the action will:

1. Check out the repo
2. Run `make dist` (assembles the static bundle from the committed
   `data/orbits.json` and the frontend in `web/`)
3. Call `huggingface_hub.upload_folder()` to push the contents of
   `dist/` to the HF Space, with a commit message tagged by GitHub SHA

You can watch the run live in the Actions tab. When it finishes, the
Space rebuilds itself and your catalog is live at:

```
https://YOUR_HF_USER-above-geo-artsat-catalog.hf.space
```

---

## 5. Routine updates

After the one-time setup above, every refresh of the catalog is just:

```bash
cd /Users/mickey/ciscluar/highartsat/catalog

# 1. Re-pull TLEs into ~/tles however you normally do it, then:
make build                     # parses ~/tles -> data/orbits.json

# 2. Commit the refreshed data and push.
git add data/orbits.json
git commit -m "Refresh TLE data $(date +%F)"
git push

# 3. ...nothing. The GitHub Action handles the HF upload.
```

You can preview the bundle locally before committing if you want:

```bash
make dist
cd dist && ~/.venvs/astro313/bin/python -m http.server 8000
# open http://127.0.0.1:8000/
```

Editing the frontend (`web/index.html`, `web/app.js`, `web/styles.css`)
or the Space metadata (`deploy/README.md`) also triggers the workflow on
push, because those paths are in the `paths:` filter at the top of
`sync-hf.yml`.

---

## 6. Customizing the Space page

The Space's title, theme colors, and short description live in
`catalog/deploy/README.md`. The workflow copies that file into
`dist/README.md`, which becomes the Space's front-page README on HF.

The required HF Spaces frontmatter fields are:

```yaml
---
title: Above-GEO Artsat Catalog
emoji: 🛰️
colorFrom: indigo
colorTo: yellow
sdk: static
pinned: false
short_description: xGEO, cislunar, translunar artsats from Bill Gray's TLE list
---
```

Do not remove these lines — the Space refuses to render without them.

---

## 7. Monorepo layout (optional)

If you prefer to host `catalog/` inside a larger repo (for example
keeping it next to `satid/`), the workflow needs two adjustments:

1. Move `.github/workflows/sync-hf.yml` to the **monorepo root** (GitHub
   only reads workflows from `<repo_root>/.github/workflows/`).
2. In that file, prefix the `paths:` patterns with `catalog/` and add
   `defaults.run.working-directory: catalog` to every job, e.g.:

   ```yaml
   on:
     push:
       branches: [main]
       paths:
         - 'catalog/web/**'
         - 'catalog/data/orbits.json'
         - 'catalog/deploy/**'
         - 'catalog/build.py'
         - 'catalog/Makefile'
         - 'catalog/.github/workflows/sync-hf.yml'
   ...
   jobs:
     sync:
       defaults:
         run:
           working-directory: catalog
       ...
   ```

The action body itself does not change.

---

## 8. Fallback: manual push to the HF Space

You should not need this once the action is wired up, but if HF or
GitHub Actions is down and you want to update the live Space directly:

```bash
cd catalog
make release            # build + assemble dist/

cd dist
git init -b main
git remote add hf https://huggingface.co/spaces/YOUR_HF_USER/above-geo-artsat-catalog
git fetch hf main || true
git add .
git commit -m "Manual sync"
git push hf main
```

When prompted, use your HF username and an HF write token as the
password (or run `huggingface-cli login` once).

---

## 9. Troubleshooting

| Symptom                                                                  | Fix                                                                                              |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Action fails: `secret HF_TOKEN is not set`                               | Add `HF_TOKEN` under repo Settings → Secrets and variables → Actions → Secrets.                  |
| Action fails: `variable HF_REPO_ID is not set`                           | Add `HF_REPO_ID` under the Variables tab in the same settings screen.                            |
| Action runs but Space stays empty                                        | Confirm `data/orbits.json` is actually committed: `git ls-files data/`. Re-run the action.       |
| Action fails on `make dist` with "data/orbits.json missing"              | Same as above — commit it.                                                                       |
| HF Space loads but plots are empty                                       | Open browser devtools → Network tab. The fetch falls through to `./data/orbits.json`. If that 404s, the upload was incomplete; rerun the action. |
| HF Space refuses to start                                                | Malformed YAML frontmatter in `deploy/README.md`. Check the `---` fences and field names.       |
| Action keeps re-running on unrelated pushes                              | Tighten the `paths:` filter in `sync-hf.yml`.                                                    |
| Want to sync without pushing code                                        | Actions tab → Sync to Hugging Face Space → Run workflow.                                        |
