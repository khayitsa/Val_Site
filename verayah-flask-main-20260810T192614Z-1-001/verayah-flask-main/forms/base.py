"""Base form: WTForms' own built-in messages ("This field is required." etc.)
follow the visitor's language too. Our own labels and messages use lazy()."""
from flask_wtf import FlaskForm
from wtforms.i18n import get_translations as _wtf_translations, DummyTranslations

from services.i18n import current_lang


class I18nForm(FlaskForm):
    class Meta(FlaskForm.Meta):
        def get_translations(self, form):
            if current_lang() == "es":
                return _wtf_translations(["es"])
            return DummyTranslations()
