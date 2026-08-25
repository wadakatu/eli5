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

    print("ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="<category>/YYYY-MM-DD-slug.html")
    parser.add_argument("--summary", help="one line, in Japanese, for the index")
    parser.add_argument("--lang", help="override the detected document language")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return 0
    if not args.path or not args.summary:
        parser.error("both a path and --summary are required")

    path = Path(args.path)
    rel = path.as_posix()
    doc = (ROOT / path).read_text(encoding="utf-8")

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
