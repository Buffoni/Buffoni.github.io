#!/usr/bin/env python3
"""
Build the static site into ./_site

    pip install -r requirements.txt
    python build.py            # build
    python build.py --serve    # build and preview on http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
from pathlib import Path

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
CONTENT, DATA, STATIC, TEMPLATES = (ROOT / d for d in ("content", "data", "static", "templates"))

MD_EXT = ["extra", "toc", "sane_lists", "smarty", "attr_list"]


def render_md(text: str) -> Markup:
    return Markup(md.markdown(text or "", extensions=MD_EXT))


def render_md_inline(text: str) -> Markup:
    h = md.markdown(text or "", extensions=MD_EXT)
    return Markup(re.sub(r"^<p>(.*)</p>$", r"\1", h.strip(), flags=re.S))


def read_front_matter(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if not m:
        return {}, raw
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def load_yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


# --------------------------------------------------------------------- filters
def make_author_filter(aliases: list[str]):
    keys = {re.sub(r"[^a-z]", "", a.lower()) for a in aliases}

    def fmt(authors: list[str], limit: int = 12) -> Markup:
        out = []
        for a in authors:
            esc = html.escape(a)
            if re.sub(r"[^a-z]", "", a.lower()) in keys:
                esc = f'<span class="me">{esc}</span>'
            out.append(esc)
        if len(out) > limit:
            me_idx = next((i for i, a in enumerate(out) if 'class="me"' in a), None)
            head = out[: limit - 2]
            if me_idx is not None and me_idx >= limit - 2:
                head = out[: limit - 3] + ["…", out[me_idx]]
            hidden = len(out) - len(head) - 1
            return Markup(", ".join(head) + f', <span class="etal" title="{hidden} more authors">… +{hidden}</span>, ' + out[-1])
        return Markup(", ".join(out))

    return fmt


def bibtex(p: dict) -> str:
    first = (p.get("authors") or ["anon"])[0].split()[-1]
    key = re.sub(r"[^A-Za-z]", "", first) + str(p.get("year", "")) + \
        re.sub(r"[^a-z]", "", (p.get("title", "x").split() or ["x"])[0].lower())
    kind = {"article": "article", "conference": "inproceedings", "thesis": "phdthesis", "patent": "patent"}.get(p["type"], "misc")
    fields = {"title": p.get("title"), "author": " and ".join(p.get("authors", [])), "year": p.get("year")}
    if kind == "article":
        fields["journal"] = p.get("venue")
    elif kind == "inproceedings":
        fields["booktitle"] = p.get("venue")
    elif kind == "patent":
        fields["number"] = p.get("venue")
    elif kind == "phdthesis":
        fields["school"] = "University of Florence"
    else:
        fields["howpublished"] = p.get("venue")
    if p.get("doi"):
        fields["doi"] = p["doi"]
    if p.get("arxiv"):
        fields["eprint"] = p["arxiv"]
        fields["archivePrefix"] = "arXiv"
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@{kind}{{{key},\n{body}\n}}"


def fmt_date(value, fmt="%b %Y"):
    if not value:
        return ""
    s = str(value)
    for f in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(s, f).strftime(fmt if f != "%Y" else "%Y")
        except ValueError:
            pass
    return s


# ------------------------------------------------------------------------ build
def build(style_override: str | None = None) -> None:
    profile = load_yaml(CONTENT / "profile.yml")
    research = load_yaml(CONTENT / "research.yml") or {}
    pubs = load_json(DATA / "publications.json", [])
    repos = load_json(DATA / "repos.json", [])
    metrics = load_json(DATA / "metrics.json", {})
    updated = (DATA / "last_updated.txt").read_text().strip() if (DATA / "last_updated.txt").exists() else ""

    sel_order = [str(d).lower() for d in ((load_yaml(DATA / "publications_extra.yml") or {}).get("selected") or [])]
    for p in pubs:
        p["bibtex"] = bibtex(p)
        p["sel_rank"] = sel_order.index(p["doi"]) if p.get("doi") in sel_order else 99
    # the selection is read live from publications_extra.yml (no need to wait for a data refresh)
    selected = sorted([p for p in pubs if p["sel_rank"] < 99], key=lambda p: p["sel_rank"])
    by_doi = {p["doi"]: p for p in pubs if p.get("doi")}

    def resolve(dois):
        return [by_doi[d.lower()] for d in (dois or []) if d.lower() in by_doi]

    for t in research.get("themes", []) + research.get("projects", []):
        t["papers"] = resolve(t.get("dois"))

    # software: pinned first
    pinned = [n.lower() for n in (profile.get("software") or {}).get("pinned", [])]
    excl = {n.lower() for n in (profile.get("software") or {}).get("exclude", [])}
    repos = [r for r in repos if r["name"].lower() not in excl]
    repos.sort(key=lambda r: (pinned.index(r["name"].lower()) if r["name"].lower() in pinned else 99,
                              -r.get("stars", 0)))

    # teaching
    courses = []
    for f in sorted((CONTENT / "teaching").glob("*.md")):
        if f.name.startswith("_"):
            continue
        meta, body = read_front_matter(f)
        meta["slug"] = f.stem
        meta["body"] = render_md(body)
        meta.setdefault("status", "current")
        meta.setdefault("order", 50)
        for sec in meta.get("materials") or []:
            for it in sec.get("items") or []:
                if it.get("file"):
                    it["href"] = f"/files/teaching/{f.stem}/{it['file']}"
                    fp = STATIC / "files" / "teaching" / f.stem / it["file"]
                    it["missing"] = not fp.exists()
                    if fp.exists():
                        it["size"] = fp.stat().st_size
                else:
                    it["href"] = it.get("url", "#")
                it["ext"] = Path(it["href"].split("?")[0]).suffix.lstrip(".").lower()
        meta["n_materials"] = sum(len(s.get("items") or []) for s in meta.get("materials") or [])
        courses.append(meta)
    courses.sort(key=lambda c: (c["order"], c.get("title", "")))

    # talks
    tmeta = load_json(DATA / "talks_meta.json", {})
    talks = []
    for i, t in enumerate(((load_yaml(CONTENT / "talks.yml") or {}).get("talks")) or []):
        t = dict(t)
        vid = str(t.get("youtube") or "").strip()
        m = tmeta.get(vid, {})
        t["youtube"] = vid
        t["title"] = t.get("title") or m.get("title") or ""
        t["channel"] = m.get("channel", "")
        t["date"] = str(t["date"]) if t.get("date") else ""
        if t.get("slides") and not str(t["slides"]).startswith("http"):
            t["slides"] = f"/files/talks/{t['slides']}"
        if t.get("paper"):
            t["paper_obj"] = by_doi.get(str(t["paper"]).lower())
        t["_i"] = i
        talks.append(t)
    # newest first when dated; undated ones keep their order, at the end
    talks = sorted([t for t in talks if t["date"]], key=lambda t: t["date"], reverse=True) + \
        [t for t in talks if not t["date"]]

    cv_meta, cv_body = read_front_matter(CONTENT / "cv.md")

    # stats
    years = sorted({p["year"] for p in pubs if p.get("year")}, reverse=True)
    counts = {k: sum(1 for p in pubs if p["type"] == k) for k in ("article", "conference", "preprint", "thesis", "patent")}
    first_author = sum(1 for p in pubs if p.get("authors") and
                       re.sub(r"[^a-z]", "", p["authors"][0].lower()) in
                       {re.sub(r"[^a-z]", "", a.lower()) for a in profile["author_aliases"]})

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(md=render_md, mdi=render_md_inline, authors=make_author_filter(profile["author_aliases"]),
                       date=fmt_date, tojson_attr=lambda o: json.dumps(o, ensure_ascii=False))
    style = style_override or profile.get("style", "classic")
    ctx = dict(style=style, selected=selected, profile=profile, research=research, pubs=pubs, repos=repos, metrics=metrics,
               courses=courses, talks=talks, updated=updated, years=years, counts=counts,
               first_author=first_author, build_year=dt.date.today().year,
               has_cv_pdf=(STATIC / "files" / "cv.pdf").exists())

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT)

    pages = []

    def page(template: str, path: str, **kw):
        dest = OUT / path.strip("/") / "index.html" if not path.endswith(".html") else OUT / path.strip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx, path=path, **kw), encoding="utf-8")
        if path.endswith("/"):
            pages.append(path)

    idx = f"index_{style}.html" if (TEMPLATES / f"index_{style}.html").exists() else "index.html"
    page(idx, "/", active="home")
    page("publications.html", "/publications/", active="publications", title="Publications")
    page("research.html", "/research/", active="research", title="Research")
    page("software.html", "/software/", active="software", title="Software")
    page("teaching.html", "/teaching/", active="teaching", title="Teaching")
    for c in courses:
        page("course.html", f"/teaching/{c['slug']}/", active="teaching", title=c["title"], course=c)
    page("cv.html", "/cv/", active="cv", title=cv_meta.get("title", "CV"), cv=render_md(cv_body))
    page("talks.html", "/talks/", active="talks", title="Talks")
    page("redirect.html", "/about/", target="/")
    page("404.html", "404.html", title="Page not found")

    # machine-readable extras
    (OUT / "publications.json").write_text(json.dumps(pubs, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "publications.bib").write_text("\n\n".join(p["bibtex"] for p in pubs) + "\n", encoding="utf-8")
    base = profile["site_url"].rstrip("/")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"  <url><loc>{base}{p}</loc></url>\n" for p in pages if p not in ("/about/",)) +
        "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(pages)} pages, {len(pubs)} publications, {len(courses)} courses -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--style", help="override the style set in content/profile.yml")
    a = ap.parse_args()
    build(a.style)
    if a.serve:
        import functools
        import http.server
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print("Serving on http://localhost:8000")
        http.server.ThreadingHTTPServer(("", 8000), h).serve_forever()
