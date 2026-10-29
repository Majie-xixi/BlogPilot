import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blogpost.config import AppConfig
from blogpost.ui.settings_dialog import SettingsDialog, fit_dialog_geometry


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


class SettingsSaveTests(unittest.TestCase):
    @patch('blogpost.ui.settings_dialog.config_path')
    @patch.object(AppConfig, 'save')
    def test_codex_selection_preserves_api_settings_without_saving_key(self, save, path):
        old = AppConfig(api_base_url='https://example.com/v1', model='old-model')
        secrets = Mock()
        dialog = SimpleNamespace(
            context=SimpleNamespace(config=old, secrets=secrets),
            vars={name: Mock(get=Mock(return_value=value)) for name, value in {
                'provider': 'codex', 'api_base_url': old.api_base_url, 'model': old.model,
                'api_key': 'existing-key', 'dry_run': True,
            }.items()},
            on_saved=Mock(), destroy=Mock(),
        )
        SettingsDialog._save(dialog)
        self.assertEqual(dialog.context.config.provider, 'codex')
        self.assertEqual(dialog.context.config.api_base_url, 'https://example.com/v1')
        self.assertEqual(dialog.context.config.model, 'old-model')
        secrets.set_api_key.assert_not_called()
        dialog.on_saved.assert_called_once()

    @patch('blogpost.ui.settings_dialog.config_path')
    @patch.object(AppConfig, 'save')
    def test_api_selection_saves_key_and_provider(self, save, path):
        secrets = Mock()
        dialog = SimpleNamespace(
            context=SimpleNamespace(config=AppConfig(provider='codex'), secrets=secrets),
            vars={name: Mock(get=Mock(return_value=value)) for name, value in {
                'provider': 'api', 'api_base_url': 'https://example.com/v1', 'model': 'model',
                'api_key': 'new-key', 'dry_run': True,
            }.items()},
            on_saved=Mock(), destroy=Mock(),
        )
        SettingsDialog._save(dialog)
        self.assertEqual(dialog.context.config.provider, 'api')
        secrets.set_api_key.assert_called_once_with('new-key')


if __name__ == "__main__":
    unittest.main()
