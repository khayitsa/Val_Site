"""
Admin forms. Using Flask-WTF gives every form CSRF protection automatically
and server-side validation, instead of trusting whatever a raw POST body
contains.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, DecimalField, TextAreaField,
    SelectField, BooleanField, IntegerField, SubmitField
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Email

CATEGORIES = ["Body Chain", "Hand Chain", "Waist Chain", "Anklet", "Earring"]
ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class ProductForm(FlaskForm):
    name = StringField("Product name", validators=[DataRequired(), Length(max=150)])
    category = SelectField("Category", choices=[(c, c) for c in CATEGORIES], validators=[DataRequired()])
    price = DecimalField("Price (USD)", places=2, validators=[DataRequired(), NumberRange(min=0)])
    description = TextAreaField("Description", validators=[DataRequired()])
    image = FileField("Product photo", validators=[
        Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (jpg, png, webp).")
    ])
    is_active = BooleanField("Visible on the site", default=True)
    sort_order = IntegerField("Display order", validators=[Optional(), NumberRange(min=0)], default=0)
    submit = SubmitField("Save product")


class OrderStatusForm(FlaskForm):
    status = SelectField("Status", choices=[(s, s.capitalize()) for s in ORDER_STATUSES],
                          validators=[DataRequired()])
    payment_status = SelectField("Payment", choices=[("unpaid", "Awaiting payment"), ("paid", "Paid")],
                                 validators=[DataRequired()])
    delivery_fee = DecimalField("Delivery fee (USD)", places=2, validators=[Optional(), NumberRange(min=0)])
    tracking_number = StringField("Tracking number", validators=[Optional(), Length(max=100)])
    notes = TextAreaField("Internal notes", validators=[Optional()])
    submit = SubmitField("Update order")


class OrderForm(FlaskForm):
    """For manually logging an order taken via WhatsApp/DM/in person."""
    customer_name = StringField("Customer name", validators=[DataRequired(), Length(max=150)])
    customer_email = StringField("Email", validators=[Optional(), Email(), Length(max=150)])
    customer_phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    shipping_address = StringField("Shipping address", validators=[DataRequired(), Length(max=255)])
    shipping_city = StringField("City", validators=[DataRequired(), Length(max=100)])
    shipping_country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Create order")


class OrderCustomerForm(FlaskForm):
    """Correct a customer's details on an existing order (e.g. a data-correction request)."""
    customer_name = StringField("Customer name", validators=[DataRequired(), Length(max=150)])
    customer_email = StringField("Email", validators=[Optional(), Email(), Length(max=150)])
    customer_phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    shipping_address = StringField("Shipping address", validators=[DataRequired(), Length(max=255)])
    shipping_city = StringField("City", validators=[DataRequired(), Length(max=100)])
    shipping_country = StringField("Country", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Save customer details")
