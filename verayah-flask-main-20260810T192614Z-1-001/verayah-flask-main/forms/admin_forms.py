"""
Admin forms. Using Flask-WTF gives every form CSRF protection automatically
and server-side validation, instead of trusting whatever a raw POST body
contains.
"""
from forms.base import I18nForm
from services.i18n import lazy as L
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, DecimalField, TextAreaField,
    SelectField, BooleanField, IntegerField, SubmitField
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Email

# Keep in sync with the filter links in templates/products.html (data-filter values).
CATEGORIES = ["Body Chain", "Hand Chain", "Waist Chain", "Anklet", "Earring",
              "Necklace", "Swimsuit Charm", "Bag Charm"]
DECIMAL_KW = {"type": "text", "inputmode": "decimal", "autocomplete": "off"}
ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]


class LoginForm(I18nForm):
    username = StringField(L("Username"), validators=[DataRequired(), Length(max=80)])
    password = PasswordField(L("Password"), validators=[DataRequired()])
    submit = SubmitField(L("Log in"))


class ProductForm(I18nForm):
    name = StringField(L("Product name"), validators=[DataRequired(), Length(max=150)])
    category = SelectField(L("Category"), choices=[(c, L(c)) for c in CATEGORIES], validators=[DataRequired()])
    price = DecimalField(L("Price (USD)"), places=2, validators=[DataRequired(), NumberRange(min=0)],
                         render_kw=DECIMAL_KW)
    description = TextAreaField(L("Description"), validators=[DataRequired()])
    description_es = TextAreaField(L("Description in Spanish (optional)"), validators=[Optional()])
    image = FileField(L("Product photo"), validators=[
        Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], L("Please use a JPG, PNG or WEBP photo. (iPhone tip: if it is a HEIC photo, share or export it as JPG first.)"))
    ], render_kw={"accept": ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"})
    def validate_image(self, field):
        """Check the real file signature and that it decodes, not just the extension."""
        _check_image_signature(field)

    is_active = BooleanField(L("Visible on the site"), default=True)
    sort_order = IntegerField(L("Display order"), validators=[Optional(), NumberRange(min=0)], default=0)
    submit = SubmitField(L("Save product"))


def check_upload(f):
    """Check one uploaded photo: real file signature (jpg/png/webp), not just the
    extension, and that it can actually be read. Raises ValidationError with a
    plain-English message."""
    from wtforms.validators import ValidationError
    if not f or not getattr(f, "stream", None):
        return
    head = f.stream.read(12)
    f.stream.seek(0)
    ok = (head.startswith(b"\xff\xd8\xff")
          or head.startswith(b"\x89PNG\r\n\x1a\n")
          or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))
    if not ok:
        raise ValidationError(L("That file is not a real JPG, PNG or WEBP image. (iPhone tip: share or export the photo as JPG.)"))
    from services.images import check, BadImage
    try:
        check(f.stream)
    except BadImage as exc:
        raise ValidationError(L(str(exc)))


def _check_image_signature(field):
    check_upload(field.data)


class JournalForm(I18nForm):
    title = StringField(L("Title"), validators=[DataRequired(), Length(max=200)])
    excerpt = TextAreaField(L("Short summary (shown on the Journal page)"), validators=[Optional(), Length(max=300)])
    title_es = StringField(L("Title in Spanish (optional)"), validators=[Optional(), Length(max=200)])
    excerpt_es = TextAreaField(L("Short summary in Spanish (optional)"), validators=[Optional(), Length(max=300)])
    body_es = TextAreaField(L("Story in Spanish (optional)"), validators=[Optional(), Length(max=50000)])
    body = TextAreaField(L("Story"), validators=[DataRequired(), Length(max=50000)])
    image = FileField(L("Cover photo"), validators=[
        Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], L("Please use a JPG, PNG or WEBP photo. (iPhone tip: if it is a HEIC photo, share or export it as JPG first.)"))
    ], render_kw={"accept": ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"})
    remove_image = BooleanField(L("Remove the current cover photo"))
    is_published = BooleanField(L("Published (visible on the site)"), default=False)
    submit = SubmitField(L("Save post"))

    def validate_image(self, field):
        _check_image_signature(field)


class OrderStatusForm(I18nForm):
    status = SelectField(L("Status"), choices=[(s, L(s.capitalize())) for s in ORDER_STATUSES],
                          validators=[DataRequired()])
    payment_status = SelectField(L("Payment"), choices=[("unpaid", L("Awaiting payment")), ("paid", L("Paid"))],
                                 validators=[DataRequired()])
    delivery_fee = DecimalField(L("Delivery fee (USD)"), places=2, validators=[Optional(), NumberRange(min=0)],
                                render_kw=DECIMAL_KW)
    tracking_number = StringField(L("Tracking number"), validators=[Optional(), Length(max=100)])
    notes = TextAreaField(L("Internal notes"), validators=[Optional()])
    submit = SubmitField(L("Update order"))


class OrderForm(I18nForm):
    """For manually logging an order taken via WhatsApp/DM/in person."""
    customer_name = StringField(L("Customer name"), validators=[DataRequired(), Length(max=150)])
    customer_email = StringField(L("Email"), validators=[Optional(), Email(), Length(max=150)])
    customer_phone = StringField(L("Phone"), validators=[Optional(), Length(max=50)])
    shipping_address = StringField(L("Shipping address"), validators=[DataRequired(), Length(max=255)])
    shipping_city = StringField(L("City"), validators=[DataRequired(), Length(max=100)])
    shipping_country = StringField(L("Country"), validators=[DataRequired(), Length(max=100)])
    notes = TextAreaField(L("Notes"), validators=[Optional()])
    submit = SubmitField(L("Create order"))


class OrderCustomerForm(I18nForm):
    """Correct a customer's details on an existing order (e.g. a data-correction request)."""
    customer_name = StringField(L("Customer name"), validators=[DataRequired(), Length(max=150)])
    customer_email = StringField(L("Email"), validators=[Optional(), Email(), Length(max=150)])
    customer_phone = StringField(L("Phone"), validators=[Optional(), Length(max=50)])
    shipping_address = StringField(L("Shipping address"), validators=[DataRequired(), Length(max=255)])
    shipping_city = StringField(L("City"), validators=[DataRequired(), Length(max=100)])
    shipping_country = StringField(L("Country"), validators=[DataRequired(), Length(max=100)])
    submit = SubmitField(L("Save customer details"))
