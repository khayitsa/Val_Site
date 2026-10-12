"""Helpers for the Journal: URL slugs and a small, safe text-to-HTML renderer.

Posts are written as plain text in the admin. The renderer ESCAPES everything
first, then turns a few simple patterns into HTML, so a post can never inject
scripts or arbitrary markup:

    blank line            -> new paragraph
    ## Heading            -> section heading
    ### Smaller heading   -> sub heading
    - item                -> bullet list (every line of the block starts with "- ")
    **bold**  *italic*    -> <strong> / <em>
    [text](https://...)   -> link (https/http only)
"""
import re
import unicodedata

from markupsafe import Markup, escape

from models import JournalPost


def slugify(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80].strip("-") or "post"


def unique_slug(title, exclude_id=None):
    base = slugify(title)
    slug, n = base, 2
    while True:
        q = JournalPost.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(JournalPost.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])")


def _inline(s):
    s = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener nofollow">\1</a>', s)
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _ITALIC.sub(r"<em>\1</em>", s)
    return s


def render_body(text):
    safe = str(escape((text or "").replace("\r\n", "\n").replace("\r", "\n"))).strip()
    if not safe:
        return Markup("")
    out = []
    for block in re.split(r"\n\s*\n", safe):
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            out.append(f"<h3>{_inline(block[4:].strip())}</h3>")
        elif block.startswith("## "):
            out.append(f"<h2>{_inline(block[3:].strip())}</h2>")
        else:
            lines = block.split("\n")
            if all(l.startswith("- ") for l in lines):
                items = "".join(f"<li>{_inline(l[2:].strip())}</li>" for l in lines)
                out.append(f"<ul>{items}</ul>")
            else:
                out.append("<p>" + "<br>".join(_inline(l) for l in lines) + "</p>")
    return Markup("\n".join(out))
