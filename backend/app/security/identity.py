def normalize_email(email: str) -> str:
    """Return the canonical value stored in User.normalized_email."""

    return email.strip().casefold()
