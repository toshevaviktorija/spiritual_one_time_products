from django.core.validators import EmailValidator, RegexValidator

# Django permits local domains; customer delivery requires a dotted domain.
validate_public_email = RegexValidator(
    r'^[^\s@]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$',
    'Enter a complete email address, for example name@example.com.',
)


def validate_delivery_email(value):
    EmailValidator()(value)
    validate_public_email(value)
