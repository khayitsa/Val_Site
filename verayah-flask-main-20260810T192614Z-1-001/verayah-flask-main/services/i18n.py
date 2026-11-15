"""English / Spanish switch for the public site and the admin portal.

How it works
------------
* English is the source language. Every visible English phrase in a template or
  in Python goes through a small helper, and the Spanish wording for it lives in
  services/translations_es.py (a plain {english: spanish} dictionary).
* A phrase with no Spanish entry simply shows in English, so a missing
  translation can never break a page.
* The visitor's choice is kept in a small "lang" cookie (one year). The first
  time someone arrives, DEFAULT_LANG decides: "auto" follows the browser's
  language, "en" / "es" force one.
* Long legal pages are written out in full in Spanish as separate templates
  (privacy.es.html, ...). render_page() picks the Spanish file when it exists.

Helpers
-------
  _(text, **vars)    plain text   (the value is escaped; use in templates)
  _h(text, **vars)   text that contains trusted HTML such as <a> or <strong>
  t(text, **vars)    same as _() for Python code (flash messages, emails)
  lazy(text)         for form labels and validator messages, which are created
                     before a request exists; translated when they are shown
  loc(obj, "field")  database text that has an optional Spanish copy
                     (field_es), falling back to the English field
"""
import re
from datetime import datetime

from flask import current_app, has_request_context, request
from markupsafe import Markup, escape

from services.translations_es import ES

LANGS = ("en", "es")
LANG_NAMES = {"en": "English", "es": "Español"}
COOKIE = "lang"
ONE_YEAR = 60 * 60 * 24 * 365

MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MONTHS_ES_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def current_lang():
    """'en' or 'es' for the request being served (English outside a request)."""
    if not has_request_context():
        return "en"
    saved = request.cookies.get(COOKIE)
    if saved in LANGS:
        return saved
    default = (current_app.config.get("DEFAULT_LANG") or "auto").lower()
    if default in LANGS:
        return default
    best = request.accept_languages.best_match(LANGS)
    return best if best in LANGS else "en"


def _lookup(text, lang):
    """A key may end in "##context" to tell apart two English phrases that are the
    same word but need different Spanish (e.g. "Collection##section"). The
    context part is never shown."""
    if lang == "es" and text in ES:
        return ES[text]
    return text.split("##", 1)[0]


def translate(text, lang=None, **kw):
    """Plain string in the given (or current) language, with {name} fields filled in."""
    s = _lookup(text, lang or current_lang())
    return s.format(**kw) if kw else s


# --- helpers used from Python ------------------------------------------------

def t(text, **kw):
    return translate(text, None, **kw)


class LazyText:
    """A phrase that is translated at the moment it is turned into text.

    Form labels and validator messages are created when the app starts, long
    before anyone has chosen a language. This waits until the page is drawn."""
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text

    def __str__(self):
        return translate(self.text)

    def __html__(self):
        return str(escape(str(self)))

    def __repr__(self):
        return f"LazyText({self.text!r})"


def lazy(text):
    return LazyText(text)


# --- helpers used from templates ---------------------------------------------

def tmpl_text(text, **kw):
    s = _lookup(text, current_lang())
    if kw:
        return Markup(escape(s)).format(**kw)  # Markup.format escapes plain values
    return s


def tmpl_html(text, **kw):
    s = _lookup(text, current_lang())
    return Markup(s).format(**kw) if kw else Markup(s)


def loc(obj, field):
    """Database text with an optional Spanish copy: obj.<field>_es, else obj.<field>."""
    base = getattr(obj, field, None)
    if current_lang() == "es":
        es = getattr(obj, field + "_es", None)
        if es and str(es).strip():
            return es
    return base


_MONTH_TOKEN = re.compile(r"%([Bb])")


def fdate(value, fmt="%d %b %Y"):
    """strftime with Spanish month names when the page is in Spanish."""
    if not value:
        return ""
    if current_lang() == "es":
        def month(m):
            names = MONTHS_ES if m.group(1) == "B" else MONTHS_ES_SHORT
            return names[value.month - 1]
        fmt = _MONTH_TOKEN.sub(month, fmt)
    return value.strftime(fmt)


def render_page(template_name, **context):
    """render_template, but use <name>.es.html when the visitor reads Spanish and it exists."""
    from flask import render_template
    if current_lang() == "es" and template_name.endswith(".html"):
        es_name = template_name[:-5] + ".es.html"
        try:
            current_app.jinja_env.get_template(es_name)
            return render_template(es_name, **context)
        except Exception as exc:  # noqa: BLE001 - only "no such template" is expected
            if exc.__class__.__name__ != "TemplateNotFound":
                raise
    return render_template(template_name, **context)


def switch_url(code):
    """Link that switches language and returns to the page being viewed."""
    from flask import url_for
    here = request.full_path.rstrip("?") if has_request_context() else "/"
    return url_for("main.set_language", code=code, next=here)


def init_app(app):
    """Wire the helpers into Jinja and add the /lang/<code> route's context."""
    app.jinja_env.filters["fdate"] = fdate

    @app.context_processor
    def _i18n_context():
        return {
            "_": tmpl_text,
            "_h": tmpl_html,
            "t": t,
            "lang": current_lang(),
            "other_lang": "es" if current_lang() == "en" else "en",
            "LANG_NAMES": LANG_NAMES,
            "loc": loc,
            "switch_url": switch_url,
        }
