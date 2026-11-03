import unittest
from unittest.mock import Mock, patch
from blogpost.ui.settings_dialog import fit_dialog_geometry


class SettingsDialogGeometryTests(unittest.TestCase):
    def test_dialog_is_centered_on_parent_monitor(self):
        from blogpost.ui.settings_dialog import place_dialog
        parent = Mock()
        parent.winfo_rootx.return_value = 2100
        parent.winfo_rooty.return_value = 100
        parent.winfo_width.return_value = 1000
        parent.winfo_height.return_value = 800
        dialog = Mock()
        with patch('blogpost.ui.settings_dialog.monitor_work_area', return_value=(1920, 0, 3840, 1040)):
            place_dialog(dialog, parent, (600, 400))
        dialog.geometry.assert_called_once_with('600x400+2300+300')

    def test_large_dialog_is_fitted_inside_small_work_area(self):
        width, height, x, y = fit_dialog_geometry(
            parent=(0, 0, 1000, 700),
            work_area=(0, 0, 1024, 600),
        )

        self.assertEqual((width, height), (650, 568))
        self.assertGreaterEqual(x, 16)
        self.assertGreaterEqual(y, 16)
        self.assertLessEqual(x + width, 1008)
        self.assertLessEqual(y + height, 584)

    def test_dialog_is_centered_when_space_is_available(self):
        geometry = fit_dialog_geometry(
            parent=(100, 50, 1000, 800),
            work_area=(0, 0, 1920, 1040),
        )

        self.assertEqual(geometry, (650, 760, 275, 70))


if __name__ == "__main__":
    unittest.main()
