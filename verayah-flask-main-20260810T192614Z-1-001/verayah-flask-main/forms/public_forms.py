"""Forms for the public site. Flask-WTF adds CSRF protection to each one."""
from forms.base import I18nForm
from services.i18n import lazy as L
from wtforms import (
    StringField, PasswordField, TextAreaField, SelectField, BooleanField,
    RadioField, SubmitField
)
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo

INQUIRY_TYPES = ["General Inquiry", "Custom Jewellery", "Order Question", "Wholesale"]


class ContactForm(I18nForm):
    name = StringField(L("Name"), validators=[DataRequired(), Length(max=150)])
    email = StringField(L("Email"), validators=[DataRequired(), Email(), Length(max=150)])
    inquiry_type = SelectField(L("Inquiry Type"), choices=[(t, L(t)) for t in INQUIRY_TYPES])
    message = TextAreaField(L("Your Message"), validators=[DataRequired(), Length(max=4000)])


class SubscribeForm(I18nForm):
    email = StringField(L("Email"), validators=[DataRequired(), Email(), Length(max=150)])
    name = StringField(L("Name (optional)"), validators=[Optional(), Length(max=150)])
    # Unticked by default: nobody is signed up to a list they did not choose.
    newsletter = BooleanField(L("Newsletter - new pieces and ocean stories"))
    sneak_peek = BooleanField(L("Sneak-peek club - early looks at new collections"))


class RegisterForm(I18nForm):
    name = StringField(L("Full name"), validators=[DataRequired(), Length(max=150)])
    email = StringField(L("Email"), validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField(L("Phone / WhatsApp (optional)"), validators=[Optional(), Length(max=50)])
    password = PasswordField(L("Password"), validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField(L("Confirm password"), validators=[DataRequired(), EqualTo("password", L("Passwords do not match."))])
    # Marketing is a SEPARATE, optional choice - not bundled with creating an account.
    marketing = BooleanField(L("Also send me the newsletter and sneak-peek club emails (optional)"))
    accept = BooleanField(L("I have read the Privacy Policy and Terms"), validators=[DataRequired(L("Please confirm to create an account."))])


class CustomerLoginForm(I18nForm):
    email = StringField(L("Email"), validators=[DataRequired(), Email(), Length(max=150)])
    password = PasswordField(L("Password"), validators=[DataRequired()])


class AccountDetailsForm(I18nForm):
    name = StringField(L("Full name"), validators=[DataRequired(), Length(max=150)])
    phone = StringField(L("Phone / WhatsApp"), validators=[Optional(), Length(max=50)])
    shipping_address = StringField(L("Delivery address"), validators=[Optional(), Length(max=255)])
    shipping_city = StringField(L("City"), validators=[Optional(), Length(max=100)])


class DeleteAccountForm(I18nForm):
    password = PasswordField(L("Confirm your password"), validators=[DataRequired()])


class CheckoutForm(I18nForm):
    name = StringField(L("Full name"), validators=[DataRequired(), Length(max=150)])
    email = StringField(L("Email"), validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField(L("Phone / WhatsApp"), validators=[DataRequired(), Length(max=50)])
    delivery_method = RadioField(L("Delivery"), choices=[("courier", L("Delivery within Panama (Uno Express)")),
                                                      ("collection", L("Collection"))],
                                 default="courier", validators=[DataRequired()])
    shipping_address = StringField(L("Delivery address"), validators=[Optional(), Length(max=255)])
    shipping_city = StringField(L("City"), validators=[Optional(), Length(max=100)])
    payment_method = RadioField(L("Payment"), choices=[("yappy", L("Yappy")), ("bank_transfer", L("Bank transfer"))],
                                default="yappy", validators=[DataRequired()])
    notes = TextAreaField(L("Notes (optional)"), validators=[Optional(), Length(max=1000)])
    save_details = BooleanField(L("Save these details to my account"))
    # Separate, unticked-by-default marketing choices.
    newsletter = BooleanField(L("Newsletter"))
    sneak_peek = BooleanField(L("Sneak-peek club"))
    accept = BooleanField(L("I have read and accept the Terms and Privacy Policy"),
                          validators=[DataRequired(L("Please accept the Terms and Privacy Policy to place your order."))])

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        # Courier delivery needs an address. (Done here rather than in a
        # per-field validator because Optional() would skip it when empty.)
        if self.delivery_method.data == "courier":
            for field, msg in ((self.shipping_address, L("Please enter a delivery address.")),
                               (self.shipping_city, L("Please enter a city."))):
                if not (field.data or "").strip():
                    field.errors = list(field.errors) + [msg]
                    ok = False
        return ok
