import unittest
from pathlib import Path
import tempfile

from blogpost.secrets import DpapiSecretStore, MemorySecretStore


class SecretTests(unittest.TestCase):
    def test_memory_secret_store_round_trip(self):
        store = MemorySecretStore()
        store.set_api_key("secret")
        self.assertEqual(store.get_api_key(), "secret")
        store.delete_api_key()
        self.assertIsNone(store.get_api_key())

    def test_dpapi_store_does_not_write_plaintext(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "api-key.bin"
            store = DpapiSecretStore(path)
            store.set_api_key("local-secret-value")
            self.assertNotIn(b"local-secret-value", path.read_bytes())
            self.assertEqual(store.get_api_key(), "local-secret-value")
            store.delete_api_key()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
