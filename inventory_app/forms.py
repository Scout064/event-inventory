from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, FileField, DateField
)
from wtforms.validators import (
    DataRequired, Length, Optional, Email,
    EqualTo, Regexp
)
from inventory_app.security import ReservedUsername


class SetupForm(FlaskForm):
    app_domain = StringField(
        "App Domain (e.g., inventory.example.com)",
        validators=[DataRequired()],
        default="localhost:8000"
    )
    db_host = StringField("DB Host", validators=[DataRequired()], default="db")
    db_port = StringField("DB Port", validators=[DataRequired()], default="3306")
    db_name = StringField(
        "DB Name", validators=[DataRequired()], default="inventory_db"
    )
    db_user = StringField("DB User", validators=[DataRequired()], default="inventory_user")
    db_pass = PasswordField("DB Password", validators=[DataRequired()])
    admin_username = StringField(
        "Admin Username", validators=[DataRequired(), Length(min=3, max=128)], default="admin"
    )
    admin_password = PasswordField(
        "Admin Password", validators=[DataRequired(), Length(min=6)]
    )
    default_user_username = StringField(
        "Default User Username", validators=[Optional(), Length(min=3, max=128)]
    )
    default_user_password = PasswordField(
        "Default User Password", validators=[Optional(), Length(min=6)]
    )
    company_logo = FileField("Company Logo (PNG/JPEG)")
    submit = SubmitField("Initialize")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class ItemForm(FlaskForm):
    inventory_id = StringField(
        "Inventory ID",
        validators=[
            DataRequired(message="ID is required and cannot be blank"),
            Length(min=1, max=32)
        ]
    )
    name = StringField(
        "Name",
        validators=[
            DataRequired(message="Name is required and cannot be blank"),
            Length(min=1, max=120)
        ]
    )
    category = StringField("Category", validators=[Optional(), Length(max=50)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=250)])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=50)])
    manufacturer = StringField("Manufacturer", validators=[Optional(), Length(max=50)])
    model = StringField("Model", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Save")


class ProductionForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            DataRequired(message="Production name is required"),
            Length(min=1, max=32, message="Name must be between 1 and 32 characters")
        ]
    )
    date = StringField("Date (YYYY-MM-DD)", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=255, message="Notes cannot exceed 255 characters")])
    submit = SubmitField("Save")


class UserAdminForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=32, message="Username must be between 3 and 32 characters."),
            Regexp(r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ._\-]+$', message="Username contains invalid special characters.")
        ]
    )
    password = PasswordField("Password (leave blank to keep current)", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[EqualTo('password', message='Passwords must match')])
    is_admin = BooleanField("Grant Admin Privileges")
    submit = SubmitField("Save User")


class UserProfileForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=32, message="Username must be between 3 and 32 characters."),
            Regexp(
                r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ._\-]+$',
                message="Username contains invalid special characters."
            ),
            ReservedUsername()
        ]
    )
    real_name = StringField(
        "Real Name",
        validators=[
            Optional(),
            Length(max=32, message="Real name cannot exceed 32 characters."),
            Regexp(
                r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ\s.\-]+$',
                message="Real name contains invalid special characters."
            )
        ]
    )
    email = StringField(
        "E-Mail Address",
        validators=[
            Optional(),
            Email(),
            Length(max=32, message="Email cannot exceed 32 characters.")
        ]
    )
    birthday = DateField("Birthday", format='%Y-%m-%d', validators=[Optional()])
    current_password = PasswordField("Current Password", validators=[Optional()])
    password = PasswordField("New Password (leave blank to keep current)", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField("Confirm New Password", validators=[EqualTo('password', message='Passwords must match')])
    submit = SubmitField("Save Profile")

