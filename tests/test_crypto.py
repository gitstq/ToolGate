import unittest
from pathlib import Path

from toolgate.crypto import (
    Cipher, generate_master_key, generate_token, hash_token,
    load_or_create_master_key, safe_compare,
)
from toolgate.errors import CryptoError


class CryptoTests(unittest.TestCase):
    def test_roundtrip(self):
        cipher = Cipher(generate_master_key())
        secret = "sk-super-secret-值-123"
        token = cipher.encrypt(secret)
        self.assertNotIn("secret", token)
        self.assertEqual(cipher.decrypt(token), secret)

    def test_wrong_key_rejected(self):
        cipher_a = Cipher(generate_master_key())
        cipher_b = Cipher(generate_master_key())
        token = cipher_a.encrypt("hello")
        with self.assertRaises(CryptoError):
            cipher_b.decrypt(token)

    def test_persisted_key(self):
        import tempfile
        path = Path(tempfile.mkdtemp()) / "master.key"
        key1 = load_or_create_master_key(path)
        key2 = load_or_create_master_key(path)
        self.assertEqual(key1, key2)
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_invalid_key(self):
        with self.assertRaises(CryptoError):
            Cipher(b"not-a-key")

    def test_token_hashing_and_compare(self):
        t = generate_token()
        self.assertEqual(hash_token(t), hash_token(t))
        self.assertNotEqual(hash_token(t), hash_token(t + "x"))
        self.assertTrue(safe_compare("abc", "abc"))
        self.assertFalse(safe_compare("abc", "abd"))


if __name__ == "__main__":
    unittest.main()
