import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blogpost.config import AppConfig
from blogpost.ui.main_window import MainWindow


class HomeModeTests(unittest.TestCase):
    def test_switch_saves_and_updates_context_only_after_success(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            context = SimpleNamespace(config=AppConfig())
            window = SimpleNamespace(context=context, running=False, refresh=Mock(), root=Mock())
            with patch('blogpost.ui.main_window.config_path', return_value=path), patch('blogpost.ui.main_window.messagebox.askyesno', return_value=True):
                MainWindow.toggle_dry_run(window)
            self.assertFalse(context.config.dry_run)
            self.assertFalse(AppConfig.load(path).dry_run)
            window.refresh.assert_called_once()

    def test_declined_or_failed_switch_preserves_config(self):
        context = SimpleNamespace(config=AppConfig())
        window = SimpleNamespace(context=context, running=False, refresh=Mock(), root=Mock())
        with patch('blogpost.ui.main_window.messagebox.askyesno', return_value=False):
            MainWindow.toggle_dry_run(window)
        self.assertTrue(context.config.dry_run)
        with patch('blogpost.ui.main_window.messagebox.askyesno', return_value=True), patch.object(AppConfig, 'save', side_effect=OSError('disk')), patch('blogpost.ui.main_window.messagebox.showerror'):
            MainWindow.toggle_dry_run(window)
        self.assertTrue(context.config.dry_run)

    def test_running_task_blocks_switch(self):
        window = SimpleNamespace(context=SimpleNamespace(config=AppConfig()), running=True, refresh=Mock(), root=Mock())
        with patch('blogpost.ui.main_window.messagebox.showinfo'):
            MainWindow.toggle_dry_run(window)
        self.assertTrue(window.context.config.dry_run)
