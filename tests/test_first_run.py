from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from blogpost.ui.first_run import ensure_data_directory


class FirstRunTests(unittest.TestCase):
    def test_existing_explicit_directory_is_initialized_without_prompt(self):
        with tempfile.TemporaryDirectory() as root:
            selected = Path(root)
            with (
                patch("blogpost.ui.first_run.configured_data_dir", return_value=selected),
                patch("blogpost.ui.first_run.initialize_data_dir") as initialize,
                patch("blogpost.ui.first_run.filedialog.askdirectory") as chooser,
            ):
                self.assertTrue(ensure_data_directory(Mock()))

            initialize.assert_called_once_with(selected)
            chooser.assert_not_called()

    def test_new_install_saves_selected_directory(self):
        with tempfile.TemporaryDirectory() as root:
            selected = Path(root) / "BlogPilotData"
            with (
                patch("blogpost.ui.first_run.configured_data_dir", return_value=None),
                patch("blogpost.ui.first_run.filedialog.askdirectory", return_value=str(selected)),
                patch("blogpost.ui.first_run.save_data_dir") as save,
            ):
                self.assertTrue(ensure_data_directory(Mock()))

            save.assert_called_once_with(selected)

    def test_cancel_stops_startup_without_creating_data(self):
        with (
            patch("blogpost.ui.first_run.configured_data_dir", return_value=None),
            patch("blogpost.ui.first_run.filedialog.askdirectory", return_value=""),
            patch("blogpost.ui.first_run.save_data_dir") as save,
        ):
            self.assertFalse(ensure_data_directory(Mock()))

        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
