# buffoni.github.io

Personal academic website of Lorenzo Buffoni — <https://buffoni.github.io>

A small, dependency-light static site: content lives in YAML/Markdown, a Python script
builds plain HTML, and a GitHub Action **refreshes publications and repositories every
Monday** and redeploys.

## One-time setup

1. Replace the contents of the `Buffoni.github.io` repository with this folder and push to `main`.
2. In the repository go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
3. Open the **Actions** tab → *Update data & deploy site* → **Run workflow** to do the first refresh.

From then on every push redeploys the site, and the weekly run keeps publications,
citation counts and the software list current.

## Where things live

| What | File |
|---|---|
| Name, bio, links, research interests | `content/profile.yml` |
| Research themes and projects (ThermoQT…) | `content/research.yml` |
| Recorded talks (YouTube) | `content/talks.yml` (slides in `static/files/talks/`) |
| CV | `content/cv.md` (put a PDF at `static/files/cv.pdf` to add a download button) |
| Teaching pages | `content/teaching/*.md` |
| Teaching files (slides, notes, data…) | `static/files/teaching/<course-slug>/` |
| Publication tweaks (hide, add, select, override) | `data/publications_extra.yml` |
| Auto-generated data — **don't edit by hand** | `data/publications.json`, `data/repos.json`, `data/metrics.json` |
| Look & feel | `templates/*.html`, `static/css/style.css` |

## Adding teaching material

1. Copy `content/teaching/_TEMPLATE.md` to e.g. `content/teaching/2026-machine-learning.md`.
2. Fill in the header (title, programme, year, `status: current` or `past`).
3. Put the files in `static/files/teaching/2026-machine-learning/` and list them under
   `materials:` with `file: name.pdf` (or `url:` for Colab/YouTube/Moodle links).
4. Commit and push — the page appears at `/teaching/2026-machine-learning/`.

Files you list but forget to upload are flagged as *missing file* on the page.
You can do all of this from the GitHub web interface (*Add file → Upload files*).

## Adding a talk

Add a line with the video ID to `content/talks.yml` (the part after `watch?v=`), optionally
with `event`, `date`, `location`, `kind`, `slides` and `paper`. The title is fetched from
YouTube automatically when the site builds. Videos play inside the page only after the
visitor clicks, using YouTube's privacy-enhanced (no-cookie) player.

## Publications: how the auto-update works

`scripts/update_data.py` queries **OpenAlex** by your ORCID (`0000-0002-8191-3375`) for the
full list, merges duplicates (an arXiv preprint is dropped once the journal version exists),
and applies `data/publications_extra.yml`:

- `hide` — DOIs/titles to drop (front covers, data deposits, abstracts…)
- `add_dois` — your papers that OpenAlex has not linked to your ORCID
  (e.g. *Machine learning in spectral domain*, Nat. Commun. 2021)
- `selected` — what appears under *Selected publications* on the home page
- `overrides` — fix a venue name, add a `code:`/`pdf:` link or a `note:`

**Google Scholar** has no API and blocks most automated requests, so it is used only
(best effort) for the headline citation/h-index numbers; when it can't be reached the
site shows the OpenAlex figures. Keeping your ORCID profile up to date (it can auto-sync
from Crossref and arXiv) is the most reliable way to keep the list complete.

## Changing the look

Set `style:` in `content/profile.yml` to one of `classic`, `editorial`, `quantum`, `bento`
and push. Preview any style locally with `python build.py --style quantum --serve`.

## Local preview

```bash
pip install -r requirements.txt
python scripts/update_data.py   # optional: refresh data
python build.py --serve         # http://localhost:8000
```

The publication list is also exported at `/publications.bib` and `/publications.json`.
Fonts (Inter, Source Serif 4 — OFL) and icons (Font Awesome Free, Academicons) are self-hosted under `static/vendor/`.
