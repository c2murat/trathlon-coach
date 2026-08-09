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


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return _password_hash.verify(password, password_hash)
    except (PwdlibError, TypeError, ValueError):
        return False
