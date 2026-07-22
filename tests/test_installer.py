from pathlib import Path
import tempfile
import unittest

from scripts.build_msi import installer_payload


class InstallerTests(unittest.TestCase):
    def test_private_data_files_are_never_installer_payload(self):
        with tempfile.TemporaryDirectory() as root:
            dist = Path(root)
            (dist / "BlogPilot.exe").write_bytes(b"application")
            (dist / "blogpilot-data-dir.txt").write_text(r"E:\private", encoding="utf-8")
            (dist / "blogpost.db").write_bytes(b"private")

            payload = installer_payload(dist)

            self.assertEqual([item.name for item in payload], ["BlogPilot.exe"])

    def test_missing_application_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError):
                installer_payload(Path(root))


if __name__ == "__main__":
    unittest.main()
