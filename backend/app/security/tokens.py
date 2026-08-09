from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe


TOKEN_BYTES = 32


def generate_secret_token() -> str:
    return token_urlsafe(TOKEN_BYTES)


def hash_secret_token(raw_token: str) -> str:
    if not raw_token:
        raise ValueError("Token cannot be empty")
    return sha256(raw_token.encode("utf-8")).hexdigest()


def verify_secret_token(raw_token: str, expected_hash: str) -> bool:
    if not raw_token or not expected_hash:
        return False
    return compare_digest(hash_secret_token(raw_token), expected_hash)
