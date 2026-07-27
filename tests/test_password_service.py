import unittest

from services.password_service import (
    PasswordValidationError,
    hash_password,
    validate_password,
    verify_password,
)


class PasswordServiceTests(unittest.TestCase):
    def test_hash_is_salted_and_verifiable(self):
        password = "a long and unique test passphrase"
        first_hash = hash_password(password)
        second_hash = hash_password(password)

        self.assertNotEqual(first_hash, password)
        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(verify_password(first_hash, password))
        self.assertFalse(verify_password(first_hash, "wrong password"))

    def test_password_length_policy(self):
        with self.assertRaises(PasswordValidationError):
            validate_password("too short")

        with self.assertRaises(PasswordValidationError):
            validate_password("x" * 129)

        validate_password("correct horse battery staple")


if __name__ == "__main__":
    unittest.main()
