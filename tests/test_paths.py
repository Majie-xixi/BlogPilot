import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blogpost.paths import (
    DATA_DIR_ENV,
    browser_profile_dir,
    configured_data_dir,
    initialize_data_dir,
    save_data_dir,
)


class DataDirectoryTests(unittest.TestCase):
    def test_configured_data_dir_prefers_environment(self):
        with tempfile.TemporaryDirectory() as root:
            expected = Path(root).resolve()
            with patch.dict(os.environ, {DATA_DIR_ENV: str(expected)}):
                self.assertEqual(configured_data_dir(), expected)

    def test_configured_data_dir_reads_development_marker_before_registry(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            marker = base / "blogpilot-data-dir.txt"
            expected = base / "workspace"
            marker.write_text("workspace", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("blogpost.paths._data_dir_marker", return_value=marker),
                patch("blogpost.paths._registry_data_dir", return_value=base / "registry"),
            ):
                self.assertEqual(configured_data_dir(), expected.resolve())

    def test_initialize_data_dir_creates_expected_layout(self):
        with tempfile.TemporaryDirectory() as root:
            data_dir = Path(root) / "BlogPilotData"

            result = initialize_data_dir(data_dir)

            self.assertEqual(result, data_dir.resolve())
            for name in ("articles", "logs", "diagnostics", "browser-profiles", "backups"):
                self.assertTrue((data_dir / name).is_dir(), name)

    def test_save_data_dir_initializes_then_persists_location(self):
        with tempfile.TemporaryDirectory() as root:
            data_dir = Path(root) / "BlogPilotData"
            with patch("blogpost.paths._write_registry_data_dir") as writer:
                result = save_data_dir(data_dir)

            self.assertEqual(result, data_dir.resolve())
            self.assertTrue((data_dir / "articles").is_dir())
            writer.assert_called_once_with(data_dir.resolve())

    def test_browser_profile_dir_separates_browser_and_account(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "blogpost.paths.app_data_dir",
            return_value=Path(root),
        ):
            result = browser_profile_dir("account-two", "Edge")

        self.assertEqual(
            result,
            Path(root) / "browser-profiles" / "edge" / "account-two",
        )

    def test_browser_profile_dir_migrates_legacy_default_profile(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "blogpost.paths.app_data_dir",
            return_value=Path(root),
        ):
            legacy = Path(root) / "chrome-profile"
            legacy.mkdir()
            (legacy / "marker.txt").write_text("signed-in", encoding="utf-8")

            target = browser_profile_dir("default", "Chrome")

            self.assertFalse(legacy.exists())
            self.assertEqual(
                (target / "marker.txt").read_text(encoding="utf-8"),
                "signed-in",
            )

    def test_browser_profile_dir_migrates_legacy_account_profile(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "blogpost.paths.app_data_dir",
            return_value=Path(root),
        ):
            legacy = Path(root) / "chrome-profiles" / "account-two"
            legacy.mkdir(parents=True)
            (legacy / "marker.txt").write_text("signed-in", encoding="utf-8")

            target = browser_profile_dir("account-two", "Edge")

            self.assertFalse(legacy.exists())
            self.assertEqual(
                (target / "marker.txt").read_text(encoding="utf-8"),
                "signed-in",
            )

    def test_browser_profile_dir_reuses_locked_legacy_profile(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "blogpost.paths.app_data_dir",
            return_value=Path(root),
        ):
            legacy = Path(root) / "chrome-profile"
            legacy.mkdir()
            with patch.object(Path, "replace", side_effect=PermissionError("locked")):
                result = browser_profile_dir("default", "Chrome")

        self.assertEqual(result, legacy)


if __name__ == "__main__":
    unittest.main()
