"""Forms for the public site. Flask-WTF adds CSRF protection to each one."""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, TextAreaField, SelectField, BooleanField,
    RadioField, SubmitField
)
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo

INQUIRY_TYPES = ["General Inquiry", "Custom Jewellery", "Order Question", "Wholesale"]


class ContactForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    inquiry_type = SelectField("Inquiry Type", choices=[(t, t) for t in INQUIRY_TYPES])
    message = TextAreaField("Your Message", validators=[DataRequired(), Length(max=4000)])


class SubscribeForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    name = StringField("Name (optional)", validators=[Optional(), Length(max=150)])
    # Unticked by default: nobody is signed up to a list they did not choose.
    newsletter = BooleanField("Newsletter - new pieces and ocean stories")
    sneak_peek = BooleanField("Sneak-peek club - early looks at new collections")


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField("Phone / WhatsApp (optional)", validators=[Optional(), Length(max=50)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", "Passwords do not match.")])
    # Marketing is a SEPARATE, optional choice - not bundled with creating an account.
    marketing = BooleanField("Also send me the newsletter and sneak-peek club emails (optional)")
    accept = BooleanField("I have read the Privacy Policy and Terms", validators=[DataRequired("Please confirm to create an account.")])


class CustomerLoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    password = PasswordField("Password", validators=[DataRequired()])


class AccountDetailsForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    phone = StringField("Phone / WhatsApp", validators=[Optional(), Length(max=50)])
    shipping_address = StringField("Delivery address", validators=[Optional(), Length(max=255)])
    shipping_city = StringField("City", validators=[Optional(), Length(max=100)])


class DeleteAccountForm(FlaskForm):
    password = PasswordField("Confirm your password", validators=[DataRequired()])


class CheckoutForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField("Phone / WhatsApp", validators=[DataRequired(), Length(max=50)])
    delivery_method = RadioField("Delivery", choices=[("courier", "Delivery within Panama (Uno Express)"),
                                                      ("collection", "Collection")],
                                 default="courier", validators=[DataRequired()])
    shipping_address = StringField("Delivery address", validators=[Optional(), Length(max=255)])
    shipping_city = StringField("City", validators=[Optional(), Length(max=100)])
    payment_method = RadioField("Payment", choices=[("yappy", "Yappy"), ("bank_transfer", "Bank transfer")],
                                default="yappy", validators=[DataRequired()])
    notes = TextAreaField("Notes (optional)", validators=[Optional(), Length(max=1000)])
    save_details = BooleanField("Save these details to my account")
    # Separate, unticked-by-default marketing choices.
    newsletter = BooleanField("Newsletter")
    sneak_peek = BooleanField("Sneak-peek club")
    accept = BooleanField("I have read and accept the Terms and Privacy Policy",
                          validators=[DataRequired("Please accept the Terms and Privacy Policy to place your order.")])

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        # Courier delivery needs an address. (Done here rather than in a
        # per-field validator because Optional() would skip it when empty.)
        if self.delivery_method.data == "courier":
            for field, msg in ((self.shipping_address, "Please enter a delivery address."),
                               (self.shipping_city, "Please enter a city.")):
                if not (field.data or "").strip():
                    field.errors = list(field.errors) + [msg]
                    ok = False
        return ok
