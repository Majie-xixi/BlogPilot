import unittest

from blogpost.ui.settings_dialog import fit_dialog_geometry


class SettingsDialogGeometryTests(unittest.TestCase):
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
