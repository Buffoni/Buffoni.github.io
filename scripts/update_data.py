#!/usr/bin/env python3
"""
Refresh the site's data files from public sources.

    python scripts/update_data.py            # update everything
    python scripts/update_data.py --only pubs

Sources
-------
* OpenAlex  (by ORCID)     -> data/publications.json, data/metrics.json
* GitHub    (public repos) -> data/repos.json
* Google Scholar (optional, best effort) -> citation metrics in data/metrics.json
* YouTube oEmbed (titles of talks in content/talks.yml) -> data/talks_meta.json

Google Scholar has no API and often blocks automated requests (especially
from CI runners), so it is only used for the headline metrics and the script
never fails because of it: if Scholar is unreachable, the previous values are
kept. OpenAlex is the authoritative source for the publication list.

Manual control lives in data/publications_extra.yml:
    hide:      DOIs or titles to drop
    add_dois:  DOIs missing from your ORCID/OpenAlex profile (fetched from OpenAlex)
    manual:    complete entries for anything not indexed anywhere
    selected:  DOIs shown as "Selected publications" on the home page
    overrides: per-DOI field overrides (e.g. a better venue name, a PDF/code link)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTENT = ROOT / "content"

UA = {"User-Agent": "academic-site-updater (mailto:{email})"}


def load_profile() -> dict:
    return yaml.safe_load((CONTENT / "profile.yml").read_text(encoding="utf-8"))


def load_extra() -> dict:
    p = DATA / "publications_extra.yml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    d = d or {}
    for k in ("hide", "add_dois", "manual", "selected"):
        d[k] = d.get(k) or []
    d["overrides"] = d.get("overrides") or {}
    return d


# --------------------------------------------------------------------------- utils
def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def norm_doi(d: str | None) -> str | None:
    if not d:
        return None
    d = d.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


TYPE_MAP = {
    "article": "article",
    "review": "article",
    "letter": "article",
    "book-chapter": "chapter",
    "conference-paper": "conference",
    "proceedings-article": "conference",
    "preprint": "preprint",
    "posted-content": "preprint",
    "dissertation": "thesis",
    "software": "software",
    "dataset": "dataset",
}
# lower number = preferred when the same work appears several times
TYPE_RANK = {"article": 0, "chapter": 1, "conference": 1, "thesis": 2, "patent": 2,
             "preprint": 3, "software": 4, "dataset": 4, "other": 5}
PEER_REVIEWED = {"article", "chapter", "conference"}


def arxiv_id(rec: dict) -> str | None:
    blob = " ".join(str(x) for x in (rec.get("doi"), rec.get("url"), rec.get("pdf")) if x)
    m = re.search(r"arxiv[./:](?:abs/)?(\d{4}\.\d{4,5})", blob, re.I)
    return m.group(1) if m else None


# ------------------------------------------------------------------------ OpenAlex
def openalex_work_to_rec(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    venue = src.get("display_name") or ""
    venue = venue.replace(" (Cornell University)", "")
    best = w.get("best_oa_location") or {}
    doi = norm_doi(w.get("doi"))
    rec = {
        "title": (w.get("title") or "").strip(),
        "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "venue": venue,
        "type": TYPE_MAP.get(w.get("type"), "other"),
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w.get("id")),
        "pdf": best.get("pdf_url"),
        "citations": w.get("cited_by_count", 0),
        "openalex": w.get("id"),
    }
    # Use arXiv as venue label for preprints
    if rec["type"] == "preprint" and not rec["venue"]:
        rec["venue"] = "Preprint"
    ax = arxiv_id(rec)
    if ax:
        rec["arxiv"] = ax
    return rec


SELECT = ("id,doi,title,publication_year,publication_date,type,primary_location,"
          "best_oa_location,authorships,cited_by_count")


def fetch_openalex_works(orcid: str, email: str) -> list[dict]:
    out, cursor = [], "*"
    while cursor:
        r = requests.get(
            "https://api.openalex.org/works",
            params={"filter": f"author.orcid:{orcid}", "per_page": 200,
                    "cursor": cursor, "select": SELECT, "mailto": email},
            headers=UA, timeout=60)
        r.raise_for_status()
        j = r.json()
        out += [openalex_work_to_rec(w) for w in j["results"]]
        cursor = j["meta"].get("next_cursor")
        if not j["results"]:
            break
    return out


def fetch_openalex_dois(dois: list[str], email: str) -> list[dict]:
    out = []
    for d in dois:
        d = norm_doi(d)
        try:
            r = requests.get(f"https://api.openalex.org/works/doi:{d}",
                             params={"select": SELECT, "mailto": email},
                             headers=UA, timeout=60)
            r.raise_for_status()
            out.append(openalex_work_to_rec(r.json()))
        except Exception as e:  # noqa: BLE001
            print(f"  ! could not fetch {d}: {e}", file=sys.stderr)
    return out


def fetch_openalex_author(orcid: str, email: str) -> dict:
    r = requests.get(f"https://api.openalex.org/authors/orcid:{orcid}",
                     params={"mailto": email}, headers=UA, timeout=60)
    r.raise_for_status()
    a = r.json()
    s = a.get("summary_stats") or {}
    return {"works": a.get("works_count"), "citations": a.get("cited_by_count"),
            "h_index": s.get("h_index"), "i10_index": s.get("i10_index")}


# ------------------------------------------------------------------ Google Scholar
def fetch_scholar_metrics(user: str) -> dict | None:
    """Best effort: parse the public profile's metrics table."""
    try:
        r = requests.get("https://scholar.google.com/citations",
                         params={"user": user, "hl": "en"},
                         headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"},
                         timeout=30)
        if r.status_code != 200:
            return None
        vals = re.findall(r'<td class="gsc_rsb_std">(\d+)</td>', r.text)
        if len(vals) >= 5:
            return {"citations": int(vals[0]), "h_index": int(vals[2]),
                    "i10_index": int(vals[4])}
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------- merge & clean up
def process(records: list[dict], extra: dict) -> list[dict]:
    hide = {norm_doi(h) or "" for h in extra["hide"]} | {norm_title(h) for h in extra["hide"]}
    selected = {norm_doi(s) for s in extra["selected"]}
    overrides = {norm_doi(k): v for k, v in extra["overrides"].items()}

    recs = []
    for r in records + [dict(m) for m in extra["manual"]]:
        r = dict(r)
        r["doi"] = norm_doi(r.get("doi"))
        r.setdefault("type", "other")
        if not r.get("title"):
            continue
        if (r["doi"] and r["doi"] in hide) or norm_title(r["title"]) in hide:
            continue
        if r["doi"] in overrides:
            r.update(overrides[r["doi"]])
        if not r.get("arxiv"):
            ax = arxiv_id(r)
            if ax:
                r["arxiv"] = ax
        if r.get("doi") and not r.get("url"):
            r["url"] = f"https://doi.org/{r['doi']}"
        r["selected"] = bool(r.get("selected")) or (r["doi"] in selected)
        recs.append(r)

    # De-duplicate: same DOI, or same title where at most one is peer reviewed
    # (keeps e.g. a NeurIPS paper *and* its journal version, but drops the arXiv copy).
    by_doi: dict[str, dict] = {}
    for r in recs:
        k = r["doi"] or f"t:{norm_title(r['title'])}:{r.get('year')}"
        if k not in by_doi or (r.get("citations") or 0) > (by_doi[k].get("citations") or 0):
            by_doi[k] = r
    groups: dict[str, list[dict]] = {}
    for r in by_doi.values():
        groups.setdefault(norm_title(r["title"]), []).append(r)
    final = []
    for g in groups.values():
        g.sort(key=lambda r: (TYPE_RANK.get(r["type"], 5), -(r.get("year") or 0)))
        peer = [r for r in g if r["type"] in PEER_REVIEWED]
        keep = peer if peer else g[:1]
        best = keep[0]
        # carry useful links (arXiv/pdf) from the duplicates we drop
        for d in g:
            if d in keep:
                continue
            best.setdefault("arxiv", d.get("arxiv"))
            if not best.get("pdf") and d.get("pdf"):
                best["pdf"] = d["pdf"]
            best["citations"] = max(best.get("citations") or 0, d.get("citations") or 0)
            best["selected"] = best["selected"] or d.get("selected", False)
        final.extend(keep)

    final = [{k: v for k, v in r.items() if v not in (None, "", [])} for r in final]
    final.sort(key=lambda r: (r.get("year") or 0, r.get("date") or ""), reverse=True)
    return final


# ------------------------------------------------------------------------ GitHub
def fetch_repos(user: str, token: str | None, exclude: list[str]) -> list[dict]:
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(f"https://api.github.com/users/{user}/repos",
                     params={"per_page": 100, "sort": "updated", "type": "owner"},
                     headers=h, timeout=60)
    r.raise_for_status()
    excl = {e.lower() for e in exclude}
    repos = []
    for x in r.json():
        if x["fork"] or x["archived"] or x["private"] or x["name"].lower() in excl:
            continue
        repos.append({
            "name": x["name"], "description": x.get("description") or "",
            "url": x["html_url"], "homepage": x.get("homepage") or "",
            "language": x.get("language") or "", "stars": x["stargazers_count"],
            "updated": x["pushed_at"][:10], "topics": x.get("topics", []),
        })
    repos.sort(key=lambda x: (x["stars"], x["updated"]), reverse=True)
    return repos


# ------------------------------------------------------------------------ YouTube
def fetch_talks_meta(existing: dict) -> dict:
    p = CONTENT / "talks.yml"
    talks = ((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("talks") or []) if p.exists() else []
    meta = dict(existing)
    for t in talks:
        vid = str(t.get("youtube") or "").strip()
        if not vid:
            continue
        try:
            r = requests.get("https://www.youtube.com/oembed",
                             params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
                             timeout=30)
            r.raise_for_status()
            j = r.json()
            meta[vid] = {"title": j.get("title", ""), "channel": j.get("author_name", "")}
        except Exception as e:  # noqa: BLE001
            print(f"  ! YouTube {vid}: {e}")
    return meta


# -------------------------------------------------------------------------- main
def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> None:
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["pubs", "repos", "metrics", "talks"])
    args = ap.parse_args()

    prof = load_profile()
    ids = prof.get("ids", {})
    email = prof.get("email") or "anonymous@example.org"
    UA["User-Agent"] = UA["User-Agent"].format(email=email)
    today = dt.date.today().isoformat()

    if args.only in (None, "pubs"):
        print("Publications (OpenAlex)…")
        extra = load_extra()
        recs = fetch_openalex_works(ids["orcid"], email)
        recs += fetch_openalex_dois(extra["add_dois"], email)
        pubs = process(recs, extra)
        print(f"  {len(recs)} raw records -> {len(pubs)} publications")
        if len(pubs) < 5:
            sys.exit("Suspiciously few publications; refusing to overwrite data.")
        write_json(DATA / "publications.json", pubs)

    if args.only in (None, "metrics"):
        print("Metrics…")
        mpath = DATA / "metrics.json"
        metrics = json.loads(mpath.read_text()) if mpath.exists() else {}
        try:
            metrics["openalex"] = fetch_openalex_author(ids["orcid"], email) | {"updated": today}
        except Exception as e:  # noqa: BLE001
            print(f"  ! OpenAlex author: {e}")
        if ids.get("google_scholar"):
            s = fetch_scholar_metrics(ids["google_scholar"])
            if s:
                metrics["scholar"] = s | {"updated": today}
            else:
                print("  ! Google Scholar not reachable; keeping previous values")
        write_json(mpath, metrics)

    if args.only in (None, "repos") and ids.get("github"):
        print("Repositories (GitHub)…")
        try:
            repos = fetch_repos(ids["github"], os.environ.get("GITHUB_TOKEN"),
                                prof.get("software", {}).get("exclude", []))
            write_json(DATA / "repos.json", repos)
        except Exception as e:  # noqa: BLE001
            print(f"  ! GitHub: {e}")

    if args.only in (None, "talks"):
        print("Talks (YouTube)…")
        tpath = DATA / "talks_meta.json"
        old = json.loads(tpath.read_text()) if tpath.exists() else {}
        write_json(tpath, fetch_talks_meta(old))

    (DATA / "last_updated.txt").write_text(today + "\n")


if __name__ == "__main__":
    main()
