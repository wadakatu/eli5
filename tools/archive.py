#!/usr/bin/env python3
"""Assemble a generated eli5 explainer into a published page, and rebuild the index.

An explainer is authored as a **fragment**: some head elements (`<title>`, the
description, a `<style>` block for its own drawings) followed by the body, marked
up with the `e-` vocabulary that `eli5.css` styles. Everything a page has in
common with every other page -- doctype, language, fonts, the stylesheet, the
link back to the index -- is added here, so a change to the shell is a change to
one file rather than to every article.

Nothing builds this site. GitHub Pages is set to deploy the branch, and a
`.nojekyll` file stops it from running Jekyll over it, so what is committed is
exactly what is served. `index.html` is therefore a real file, written by this
script from what is on disk -- which also means it can be opened and checked
locally, which a Liquid template could not be.

    python3 tools/archive.py <category>/2026-01-02-slug.html --summary "一行"
    python3 tools/archive.py --reindex      # rebuild index.html from disk
    python3 tools/archive.py --rebuild      # re-apply the shell to every page
    python3 tools/archive.py --scan         # audit every page for private names
    python3 tools/archive.py --selftest
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages.json"
INDEX = ROOT / "index.html"

BACK_LINK = '<a class="eli5-up" href="../">&larr; eli5</a>'

# Every line the shell contributes, in order. Assembly inserts them; `strip_shell`
# removes exactly these, which is what makes re-running this script idempotent
# and lets the shell change without editing a single article.
SHELL_HEAD = [
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<link rel="preconnect" href="https://fonts.googleapis.com">',
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=DM+Mono:wght@400;500&family=Zen+Kaku+Gothic+New:wght@400;500;700&"
    'family=Zen+Maru+Gothic:wght@500;700&display=swap">',
    '<link rel="stylesheet" href="../eli5.css">',
]

# Elements the parser keeps in the head. The first tag outside this set is where
# the body begins -- the same rule a browser applies.
HEAD_TAGS = {"title", "link", "meta", "style", "script", "base", "noscript"}
RAW_TEXT = {"title", "style", "script", "noscript"}

CJK = re.compile(r"[぀-ヿ一-鿿]")

# Kept outside every repository: a list of private names would leak the same
# thing it protects if it lived in a public repo.
PRIVATE_TERMS = Path.home() / ".config" / "eli5" / "private-terms.txt"

# Matched against the rendered prose only, never the markup -- a stylesheet full
# of `#16332e` would otherwise read as a page full of ticket numbers.
LEAK_PATTERNS = {
    "ticket reference": r"(?:PR|pull request|issue)\s*#?\s*\d+|#\d{2,}",
    "repository URL": r"github\.com/[\w.\-]+/[\w.\-]+",
    "local path": r"/Users/[\w.\-]+|~/www/[\w.\-/]*",
    "email address": r"[\w.\-]+@[\w.\-]+\.[a-z]{2,}",
    "internal host": r"\b[\w\-]+\.(?:local|internal|corp|test|lan)\b",
}


# --------------------------------------------------------------------------
# privacy
# --------------------------------------------------------------------------


def visible_text(doc: str) -> str:
    """The prose a reader sees: no markup, no stylesheets, no scripts, no art."""
    d = re.sub(r"(?is)<(style|script|svg)\b.*?</\1>", " ", doc)
    d = re.sub(r"(?is)<!--.*?-->", " ", d)
    return html.unescape(re.sub(r"<[^>]+>", " ", d))


def private_terms() -> list[str]:
    if not PRIVATE_TERMS.exists():
        return []
    lines = PRIVATE_TERMS.read_text(encoding="utf-8").splitlines()
    return [t.strip() for t in lines if t.strip() and not t.startswith("#")]


def find_leaks(doc: str, terms: list[str] | None = None) -> list[tuple[str, str, str]]:
    """Everything in `doc` that would identify a private repository."""
    prose = re.sub(r"\s+", " ", visible_text(doc))
    hits = []
    for kind, pattern in LEAK_PATTERNS.items():
        for m in re.finditer(pattern, prose):
            hits.append((kind, m.group(0), prose[max(0, m.start() - 40) : m.end() + 40]))

    # Terms are matched against the whole file: a private name is just as exposed
    # in an alt attribute or a comment as it is in the prose.
    low = doc.lower()
    for term in private_terms() if terms is None else terms:
        i = low.find(term.lower())
        if i >= 0:
            snippet = doc[max(0, i - 40) : i + len(term) + 40]
            hits.append(("private term", term, re.sub(r"\s+", " ", snippet)))
    return hits


def report_leaks(rel: str, leaks: list[tuple[str, str, str]]) -> bool:
    if not leaks:
        return False
    print(f"{rel}: refusing - this names a private repository", file=sys.stderr)
    for kind, hit, context in leaks:
        print(f"  [{kind}] {hit}", file=sys.stderr)
        print(f"      …{context.strip()}…", file=sys.stderr)
    print("  generalise these in the HTML, then run this again", file=sys.stderr)
    return True


# --------------------------------------------------------------------------
# the shell
# --------------------------------------------------------------------------


def split_head(doc: str) -> int:
    """Index where the body starts: the first tag that cannot live in the head."""
    scan = re.compile(r"<!--|<\s*([a-zA-Z][\w-]*)")
    i = 0
    while True:
        m = scan.search(doc, i)
        if not m:
            return len(doc)
        if m.group(0) == "<!--":
            end = doc.find("-->", m.end())
            if end < 0:
                return len(doc)
            i = end + 3
            continue

        tag = m.group(1).lower()
        if tag not in HEAD_TAGS:
            return m.start()
        if tag in RAW_TEXT:
            close = re.compile(rf"</\s*{tag}\s*>", re.I).search(doc, m.end())
            i = len(doc) if not close else close.end()
        else:
            gt = doc.find(">", m.end())
            i = len(doc) if gt < 0 else gt + 1


def strip_shell(doc: str) -> str:
    """Recover the authored fragment from an assembled page.

    Only the exact lines this script wrote are removed, so anything the author
    put in the head -- the title, the description, the drawings' styles -- comes
    back untouched and can be re-assembled against a newer shell.
    """
    m = re.search(r"(?is)<head[^>]*>(.*?)</head>.*?<body[^>]*>(.*?)</body>", doc)
    if not m:
        return doc.strip()

    head_lines = [ln for ln in m.group(1).splitlines() if ln.strip() not in SHELL_HEAD]
    body_lines = [ln for ln in m.group(2).splitlines() if ln.strip() != BACK_LINK]
    head = "\n".join(head_lines).strip()
    body = "\n".join(body_lines).strip()
    return f"{head}\n{body}".strip() if head else body


def assemble(fragment: str, lang: str | None = None) -> str:
    """Wrap an authored fragment in the shared shell."""
    fragment = strip_shell(fragment)
    cut = split_head(fragment)
    head, body = fragment[:cut].strip(), fragment[cut:].strip()
    if lang is None:
        lang = "ja" if CJK.search(fragment) else "en"

    shell = "\n".join(SHELL_HEAD)
    head_block = f"{shell}\n{head}" if head else shell
    return (
        f'<!doctype html>\n<html lang="{lang}">\n<head>\n'
        f"{head_block}\n"
        f"</head>\n<body>\n{BACK_LINK}\n{body}\n</body>\n</html>\n"
    )


def page_title(doc: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def page_summary(doc: str) -> str:
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', doc, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


# --------------------------------------------------------------------------
# the index
# --------------------------------------------------------------------------


def articles() -> list[Path]:
    """Every published page: one category directory deep, nothing hidden."""
    return sorted(
        p
        for p in ROOT.glob("*/*.html")
        if not p.parent.name.startswith((".", "_")) and p.parent.name != "tools"
    )


def load_pages() -> dict[str, dict]:
    if not PAGES.exists():
        return {}
    return {e["path"]: e for e in json.loads(PAGES.read_text(encoding="utf-8"))}


def record(rel: str, title: str, summary: str) -> None:
    entries = load_pages()
    entries[rel] = {"path": rel, "title": title, "summary": summary}
    ordered = [entries[k] for k in sorted(entries)]
    PAGES.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


INDEX_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eli5</title>
<meta name="description" content="{count} 本の絵で説明する解説。">
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.7 system-ui, sans-serif; max-width: 42rem; margin: 4rem auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 1.4rem; margin: .25rem 0 0; }}
  a.up {{ font-size: .8rem; opacity: .6; text-decoration: none; }}
  a.up:hover, a.up:focus {{ text-decoration: underline; opacity: 1; }}
  h2 {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; opacity: .55; margin: 2.5rem 0 .25rem; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ padding: .5rem 0; border-bottom: 1px solid color-mix(in srgb, currentColor 15%, transparent); }}
  time {{ opacity: .6; font-variant-numeric: tabular-nums; margin-right: .75rem; }}
  p.sum {{ margin: .15rem 0 0; font-size: .875rem; opacity: .6; }}
  p.empty {{ opacity: .6; }}
</style>
</head>
<body>
<!-- Written by tools/archive.py from what is on disk. Do not edit by hand. -->
<a class="up" href="/">&larr; wadakatu.dev</a>
<h1>eli5</h1>
{body}
</body>
</html>
"""


def build_index() -> str:
    """Render index.html from the files on disk, enriched by pages.json."""
    meta = load_pages()
    groups: dict[str, list[Path]] = {}
    for path in articles():
        groups.setdefault(path.parent.name, []).append(path)

    if not groups:
        return INDEX_TEMPLATE.format(count=0, body='<p class="empty">まだ何もありません。</p>')

    out = []
    for category in sorted(groups):
        out.append(f"<h2>{html.escape(category)}</h2>")
        out.append("<ul>")
        # newest first: the filename starts with the date
        for path in sorted(groups[category], reverse=True):
            rel = path.relative_to(ROOT).as_posix()
            date = path.stem[:10]
            slug = path.stem[11:].replace("-", " ")
            entry = meta.get(rel, {})
            label = html.escape(entry.get("title") or slug)
            out.append(
                f'  <li>\n    <a href="{html.escape(rel)}">'
                f"<time>{html.escape(date)}</time>{label}</a>"
            )
            if entry.get("summary"):
                out.append(f'    <p class="sum">{html.escape(entry["summary"])}</p>')
            out.append("  </li>")
        out.append("</ul>")

    count = sum(len(v) for v in groups.values())
    return INDEX_TEMPLATE.format(count=count, body="\n".join(out))


def reindex() -> None:
    INDEX.write_text(build_index(), encoding="utf-8")
    print(f"index.html: {len(articles())} pages")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def scan_all() -> int:
    found = False
    for path in articles():
        rel = path.relative_to(ROOT).as_posix()
        found |= report_leaks(rel, find_leaks(path.read_text(encoding="utf-8")))
    if not found:
        print("no private references found")
    return 1 if found else 0


def rebuild() -> int:
    """Re-apply the shell to every page, for when the shell itself changed."""
    for path in articles():
        doc = path.read_text(encoding="utf-8")
        out = assemble(doc)
        if out != doc:
            path.write_text(out, encoding="utf-8")
            print(f"{path.relative_to(ROOT).as_posix()}: reassembled")
    reindex()
    return 0


def archive(rel_path: str, summary: str | None, lang: str | None) -> int:
    path = ROOT / rel_path
    doc = path.read_text(encoding="utf-8")

    if report_leaks(rel_path, find_leaks(doc)):
        return 1

    out = assemble(doc, lang)
    title = page_title(out)
    summary = summary or page_summary(out)
    if not title or not summary:
        missing = " and ".join(x for x, ok in (("<title>", title), ("a summary", summary)) if not ok)
        print(f"{rel_path}: needs {missing}", file=sys.stderr)
        return 1

    path.write_text(out, encoding="utf-8")
    record(rel_path, title, summary)
    reindex()
    print(f"{rel_path}: assembled, listed as {title!r}")
    return 0


def selftest() -> None:
    fragment = (
        '<title>ロッカーの鍵</title>\n'
        '<meta name="description" content="鍵の話">\n'
        "<style>.swing{animation:none}</style>\n"
        '<div class="e-page"><p>やあ</p></div>'
    )

    out = assemble(fragment)
    assert out.startswith("<!doctype html>")
    assert 'lang="ja"' in out, "Japanese copy should be tagged ja"
    assert all(line in out for line in SHELL_HEAD), "the shell must be complete"
    assert out.index("<title>") < out.index("</head>"), "the title belongs to the head"
    assert out.index(".swing") < out.index("</head>"), "the art's styles stay in the head"
    assert out.index("</head>") < out.index('<div class="e-page">')
    body_at = re.search(r"<body[^>]*>", out).end()
    assert out.index(BACK_LINK) == body_at + 1, "the link is the first thing in the body"

    # re-assembling recovers the fragment first, so nothing stacks up
    again = assemble(out)
    assert again == out, "assembly must be idempotent"
    assert again.count(BACK_LINK) == 1
    assert again.count(SHELL_HEAD[0]) == 1

    # ...and a changed shell reaches an already-assembled page
    stale = out.replace('<link rel="stylesheet" href="../eli5.css">', "")
    assert '<link rel="stylesheet" href="../eli5.css">' in assemble(stale)

    assert strip_shell(out).strip().startswith("<title>")
    assert ".swing" in strip_shell(out), "the author's own styles survive a round trip"

    assert 'lang="en"' in assemble("<title>Notebook</title>\n<p>hi</p>")
    # a `<` inside a style block is not the start of the body
    styled = assemble("<style>@media(max-width:1px){a{}}</style>\n<p>x</p>")
    assert styled.index("</style>") < styled.index("</head>") < styled.index("<p>x</p>")

    assert page_title(fragment) == "ロッカーの鍵"
    assert page_summary(fragment) == "鍵の話"
    assert page_title("<p>none</p>") == "" and page_summary("<p>none</p>") == ""

    # --- the privacy gate ---
    def kinds(doc, terms=[]):
        return {k for k, _, _ in find_leaks(doc, terms)}

    assert kinds("<p>PR #18065 の話</p>") == {"ticket reference"}
    assert kinds("<p>issue #8234 と #8282</p>") == {"ticket reference"}
    assert kinds("<p>github.com/acme/secret-thing</p>") == {"repository URL"}
    assert kinds("<p>/Users/someone/src</p>") == {"local path"}
    assert kinds("<p>someone@example.com</p>") == {"email address"}
    assert kinds("<p>api.internal を叩く</p>") == {"internal host"}

    # a palette is not a page full of ticket numbers
    assert kinds("<style>:root{--ink:#16332e}</style><p>色の話</p>") == set()
    assert kinds('<svg><path fill="#4ecebb"/></svg><p>絵の話</p>') == set()
    assert kinds('<p style="color:#123456">文字</p>') == set()

    # configured terms are matched everywhere, prose or not
    assert kinds('<img alt="acme-api の図">', ["acme-api"]) == {"private term"}
    assert kinds("<!-- acme-api -->", ["acme-api"]) == {"private term"}
    assert kinds("<p>ACME-API</p>", ["acme-api"]) == {"private term"}
    assert find_leaks("<p>まったく無害</p>", []) == []

    print("ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="<category>/YYYY-MM-DD-slug.html")
    parser.add_argument("--summary", help="one line for the index; defaults to the page's description")
    parser.add_argument("--lang", help="override the detected document language")
    parser.add_argument("--reindex", action="store_true", help="rebuild index.html from disk")
    parser.add_argument("--rebuild", action="store_true", help="re-apply the shell to every page")
    parser.add_argument("--scan", action="store_true", help="audit every page for private names")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return 0
    if args.scan:
        return scan_all()
    if args.rebuild:
        return rebuild()
    if args.reindex:
        reindex()
        return 0
    if not args.path:
        parser.error("a path is required")
    return archive(args.path, args.summary, args.lang)


if __name__ == "__main__":
    raise SystemExit(main())
