from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError


MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 1024
_password_hash = PasswordHash.recommended()


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must contain at least {MINIMUM_PASSWORD_LENGTH} characters")
    if len(password) > MAXIMUM_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password cannot exceed {MAXIMUM_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hash.hash(password)


def verify_and_update_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    if not password or not password_hash:
        return False, None
    try:
        return _password_hash.verify_and_update(password, password_hash)
    except (PwdlibError, TypeError, ValueError):
        return False, None


def verify_password(password: str, password_hash: str) -> bool:
    return verify_and_update_password(password, password_hash)[0]


def password_hash_has_expected_format(password_hash: str) -> bool:
    return password_hash.startswith("$argon2")