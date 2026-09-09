import re
import dns.resolver
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext as _

class StrongPasswordValidator:
    def validate(self, password, user=None):
        errors = []

        if len(password) < 8:
            errors.append(_("At least 8 characters"))
        if not re.search(r'[A-Z]', password):
            errors.append(_("At least one uppercase letter"))
        if not re.search(r'[a-z]', password):
            errors.append(_("At least one lowercase letter"))
        if not re.search(r'\d', password):
            errors.append(_("At least one number"))
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append(_("At least one symbol (e.g. !@#$%)"))

        if errors:
            raise ValidationError(
                _("Password is too weak. It must include: ") + "; ".join(str(e) for e in errors) + ".",
                code='password_too_weak',
            )

    def get_help_text(self):
        return _(
            "Password must be at least 8 characters and include uppercase, "
            "lowercase, a number, and a symbol."
        )

def is_email_valid(email: str) -> tuple[bool, str]:
    """
    Returns (True, "") if email looks valid and domain can receive mail.
    Returns (False, reason) otherwise.
    """
    email = (email or "").strip()

    # 1. Basic syntax
    try:
        validate_email(email)
    except ValidationError:
        return False, "Please enter a valid email address."

    # Extra simple pattern (optional)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Please enter a valid email address."

    domain = email.split("@")[-1].lower()

    # 2. Domain MX / A record check
    try:
        # Prefer MX records (mail servers)
        dns.resolver.resolve(domain, "MX")
        return True, ""
    except Exception:
        try:
            # Some domains only have A record
            dns.resolver.resolve(domain, "A")
            return True, ""
        except Exception:
            return False, "This email domain cannot receive mail. Please use a valid email."