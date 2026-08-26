#!/usr/bin/env python3
"""Prepare a generated eli5 page for the archive.

Three things happen here, in order:

1. **Normalise.** A page authored for the Artifact tool is a fragment -- the tool
   supplies the `<!doctype>`/`<head>`/`<body>` skeleton at publish time, so the
   saved file has none. Served raw it still renders, but in quirks mode and with
   no `lang`. Fragments get wrapped; complete documents pass through untouched.

2. **Add the chrome.** Neither Jekyll nor Astro can put a layout around these
   pages -- Jekyll treats a file with no front matter as an un-rendered static
   file, and Astro's `.html` pages explicitly cannot use a layout. So the layout
   is two injected lines: `chrome.css`, which holds everything about how the
   chrome looks, and the link back to the index.

3. **Record it.** `site.static_files` exposes only paths and timestamps, never
   content, so the index cannot read a page's title or subject out of the file.
   `_data/pages.json` carries both, and the index enriches its listing from it.

Before any of that, the page is checked for anything that identifies a private
repository, and archiving is refused if it finds something. This repository is
public and the explainers are written while working in private ones, so ticket
numbers and service names leak in through footers and eyebrows without anyone
deciding to publish them.

The check is mechanical and therefore partial: it catches ticket references,
repository URLs, local paths and whatever terms are listed in
`~/.config/eli5/private-terms.txt` (kept outside any repository, so the list of
private names is itself never published). It cannot recognise an internal class
or store name it has never been told about -- **read the page's prose before
archiving it** and generalise anything that names a private repository, service,
class or ticket.

Paths in the chrome are relative because every page lives exactly one directory
deep (`<category>/YYYY-MM-DD-slug.html`), making `../` the index from anywhere.

Lives under `_tools/` so Jekyll leaves it out of the published site.

    python3 _tools/archive.py <category>/2026-01-02-slug.html --summary "一行"
    python3 _tools/archive.py --selftest
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MARKER = 'class="eli5-up"'
STYLESHEET = '<link rel="stylesheet" href="../chrome.css">'
BACK_LINK = '<a class="eli5-up" href="../">&larr; eli5</a>'

# Elements the parser is happy to keep in the head. The first tag outside this
# set is where the body starts -- the same rule the browser applies.
HEAD_TAGS = {"title", "link", "meta", "style", "script", "base", "noscript"}
# ...but these hold text, not markup, so a `<` inside them means nothing.
RAW_TEXT = {"title", "style", "script", "noscript"}

CJK = re.compile(r"[぀-ヿ一-鿿]")

# Kept outside every repository: a list of private names would leak the same
# thing it is meant to protect if it lived in a public repo.
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
            hits.append(("private term", term, re.sub(r"\s+", " ", doc[max(0, i - 40) : i + len(term) + 40])))
    return hits


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


def normalize(doc: str, lang: str | None = None) -> str:
    """Wrap a fragment into a complete document. Complete documents pass through."""
    if re.search(r"<!doctype\s", doc, re.I) or re.search(r"<html[\s>]", doc, re.I):
        return doc

    cut = split_head(doc)
    head, body = doc[:cut].strip(), doc[cut:].strip()
    if lang is None:
        lang = "ja" if CJK.search(doc) else "en"

    preamble = ['<meta name="viewport" content="width=device-width, initial-scale=1">']
    if not re.search(r'<meta\s+charset', head, re.I):
        preamble.insert(0, '<meta charset="utf-8">')

    return (
        f"<!doctype html>\n<html lang=\"{lang}\">\n<head>\n"
        + "\n".join(preamble)
        + (f"\n{head}\n" if head else "\n")
        + f"</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def add_chrome(doc: str) -> str:
    """Inject the shared back-link, or return `doc` unchanged if it already has it."""
    if MARKER in doc:
        return doc

    body = re.search(r"<body[^>]*>", doc, re.I)
    if "</head>" not in doc or not body:
        # Bailing out beats guessing: a page that silently loses its way back is
        # worse than one that fails at save time, while someone is watching.
        raise ValueError("no </head> or <body> after normalising - not an eli5 page?")

    doc = doc.replace("</head>", f"{STYLESHEET}\n</head>", 1)
    body = re.search(r"<body[^>]*>", doc, re.I)
    return doc[: body.end()] + f"\n{BACK_LINK}" + doc[body.end() :]


def page_title(doc: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def record(rel_path: str, title: str, summary: str) -> None:
    """Upsert the page's listing metadata, keeping the file sorted by path."""
    data = ROOT / "_data" / "pages.json"
    entries = json.loads(data.read_text(encoding="utf-8")) if data.exists() else []
    entries = [e for e in entries if e["path"] != rel_path]
    entries.append({"path": rel_path, "title": title, "summary": summary})
    entries.sort(key=lambda e: e["path"])

    data.parent.mkdir(exist_ok=True)
    data.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def selftest() -> None:
    fragment = '<title>ロッカーの鍵</title>\n<style>a{}</style>\n<div class="wrap">やあ</div>'
    out = normalize(fragment)
    assert out.startswith("<!doctype html>")
    assert 'lang="ja"' in out, "Japanese copy should be tagged ja"
    assert '<meta charset="utf-8">' in out
    assert out.index("<title>") < out.index("</head>"), "title belongs to the head"
    assert out.index("</head>") < out.index('<div class="wrap">'), "the div starts the body"

    assert 'lang="en"' in normalize("<title>Notebook</title>\n<p>hi</p>")
    # a `<` inside a style block must not be mistaken for the start of the body
    assert normalize("<style>@media(max-width:1px){a{}}</style>\n<p>x</p>").index(
        "</head>"
    ) > normalize("<style>@media(max-width:1px){a{}}</style>\n<p>x</p>").index("</style>")

    complete = "<!doctype html>\n<html lang=en>\n<head>\n<title>t</title>\n</head>\n<body class=x>\n<p>hi</p>\n</body>\n</html>"
    assert normalize(complete) == complete, "a complete document must pass through"

    chromed = add_chrome(normalize(fragment))
    assert chromed.index(STYLESHEET) < chromed.index("</head>")
    body_at = re.search(r"<body[^>]*>", chromed).end()
    assert chromed.index(BACK_LINK) == body_at + 1, "the link is the first thing in the body"
    assert add_chrome(chromed) == chromed, "re-archiving must not stack a second link"
    assert chromed.count(BACK_LINK) == 1

    # `<body class=x>` is still a valid anchor
    assert BACK_LINK in add_chrome(complete)

    assert page_title(fragment) == "ロッカーの鍵"
    assert page_title("<p>none</p>") == ""

    try:
        add_chrome("<p>no structure at all</p>")
    except ValueError:
        pass
    else:
        raise AssertionError("expected a refusal for a document with no head or body")

    # --- the privacy gate ---
    kinds = lambda doc, terms=[]: {k for k, _, _ in find_leaks(doc, terms)}

    assert kinds("<p>PR #18065 の話</p>") == {"ticket reference"}
    assert kinds("<p>issue #8234 と #8282</p>") == {"ticket reference"}
    assert kinds("<p>github.com/acme/secret-thing</p>") == {"repository URL"}
    assert kinds("<p>/Users/someone/src</p>") == {"local path"}
    assert kinds("<p>someone@example.com</p>") == {"email address"}
    assert kinds("<p>api.internal を叩く</p>") == {"internal host"}

    # a palette is not a page full of ticket numbers
    assert kinds("<style>:root{--ink:#16332e;--paper:#edf0ea}</style><p>色の話</p>") == set()
    assert kinds('<svg><path fill="#4ecebb"/></svg><p>絵の話</p>') == set()
    assert kinds('<p style="color:#123456">文字</p>') == set()

    # configured terms are matched everywhere, prose or not
    assert kinds('<img alt="acme-api の図">', ["acme-api"]) == {"private term"}
    assert kinds("<!-- acme-api -->", ["acme-api"]) == {"private term"}
    assert kinds("<p>ACME-API</p>", ["acme-api"]) == {"private term"}, "terms are case-insensitive"
    assert kinds("<p>まったく無害</p>", ["acme-api"]) == set()

    clean = "<title>t</title><p>キャッシュが古い答えを返していた話。</p>"
    assert find_leaks(clean, []) == []

    print("ok")


def report_leaks(rel: str, leaks: list[tuple[str, str, str]]) -> bool:
    if not leaks:
        return False
    print(f"{rel}: refusing - this names a private repository", file=sys.stderr)
    for kind, hit, context in leaks:
        print(f"  [{kind}] {hit}", file=sys.stderr)
        print(f"      …{context.strip()}…", file=sys.stderr)
    print("  generalise these in the HTML, then run this again", file=sys.stderr)
    return True


def scan_all() -> int:
    """Audit every archived page. Existing pages predate the check."""
    found = False
    for path in sorted(ROOT.glob("*/*.html")):
        if path.parts[len(ROOT.parts)].startswith("_"):
            continue
        rel = path.relative_to(ROOT).as_posix()
        found |= report_leaks(rel, find_leaks(path.read_text(encoding="utf-8")))
    if not found:
        print("no private references found")
    return 1 if found else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="<category>/YYYY-MM-DD-slug.html")
    parser.add_argument("--summary", help="one line, in Japanese, for the index")
    parser.add_argument("--lang", help="override the detected document language")
    parser.add_argument("--scan", action="store_true", help="audit every archived page and exit")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return 0
    if args.scan:
        return scan_all()
    if not args.path or not args.summary:
        parser.error("both a path and --summary are required")

    path = Path(args.path)
    rel = path.as_posix()
    doc = (ROOT / path).read_text(encoding="utf-8")

    if report_leaks(rel, find_leaks(doc)):
        return 1

    wrapped = normalize(doc, args.lang)
    out = add_chrome(wrapped)
    title = page_title(out)
    if not title:
        print(f"{rel}: no <title> - the index will fall back to the slug", file=sys.stderr)

    (ROOT / path).write_text(out, encoding="utf-8")
    record(rel, title, args.summary)

    did = [step for step, changed in
           (("normalised", wrapped != doc), ("chromed", out != wrapped)) if changed]
    print(f"{rel}: {', '.join(did) or 'already done'}, listed as {title!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
