from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from argon2.low_level import Type


PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128

_PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

_COMMON_PASSWORDS = {
    "123456789012345",
    "passwordpassword",
    "qwertyuiopasdfg",
    "letmeinletmein",
    "password123456",
}


class PasswordValidationError(ValueError):
    pass


def validate_password(password):
    if not isinstance(password, str):
        raise PasswordValidationError("password must be a string")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordValidationError(
            f"password must be at least {PASSWORD_MIN_LENGTH} characters"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordValidationError(
            f"password must be {PASSWORD_MAX_LENGTH} characters or fewer"
        )
    if password.casefold() in _COMMON_PASSWORDS:
        raise PasswordValidationError(
            "password is too common; choose a longer passphrase"
        )


def hash_password(password):
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash, password):
    if not isinstance(password_hash, str) or not isinstance(password, str):
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (
        InvalidHashError,
        VerificationError,
        VerifyMismatchError,
    ):
        return False


def password_needs_rehash(password_hash):
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except (InvalidHashError, TypeError):
        return False
