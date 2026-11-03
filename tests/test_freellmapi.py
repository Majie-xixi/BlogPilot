import unittest
from unittest.mock import Mock, patch

from blogpost.config import AppConfig, ModelConnection
from blogpost.ui.settings_state import SettingsState
from blogpost.freellmapi import FreeLLMAPIService, FreeLLMAPIError


class FreeLLMTests(unittest.TestCase):
    def test_preset_is_second_and_preserves_existing_configuration(self):
        config = AppConfig(connections=[ModelConnection('api', 'API', 'api', '自定义', 'http://example/v1', 'm'), ModelConnection('codex', 'Codex', 'codex')], active_connection_id='codex')
        state = SettingsState(config)
        self.assertEqual([c.id for c in state.connections], ['api', 'freellmapi', 'codex'])
        self.assertEqual(state.active_id, 'codex')
        self.assertEqual(len(config.connections), 2)
        self.assertEqual([c.id for c in SettingsState(state.configuration()).connections].count('freellmapi'), 1)

    def test_existing_preset_moves_to_second_without_losing_fields(self):
        config = AppConfig(connections=[ModelConnection('api', 'API', 'api', model='m', base_url='http://example'), ModelConnection('codex', 'Codex', 'codex'), ModelConnection('freellmapi', 'My gateway', 'api', base_url='http://127.0.0.1:31416/v1', model='custom')], active_connection_id='codex')
        state = SettingsState(config)
        self.assertEqual([c.id for c in state.connections], ['api', 'freellmapi', 'codex'])
        self.assertEqual((state.connections[1].name, state.connections[1].model), ('My gateway', 'custom'))

    def test_setup_uses_desktop_session_and_never_returns_session_as_key(self):
        service = FreeLLMAPIService()
        def request(port, path, data=None, token=None):
            if path == '/api/auth/status': return {'desktop': True}
            if path == '/api/auth/desktop-session': return {'token': 'session'}
            if path == '/api/settings/api-key' and token == 'session': return {'apiKey': 'unified-key'}
            raise AssertionError(path)
        with patch.object(service, '_request', side_effect=request), patch.object(service, '_listener_ports', return_value=[31416]):
            base, key = service.discover()
        self.assertEqual((base, key), ('http://127.0.0.1:31416/v1', 'unified-key'))

    def test_unavailable_instance_never_yields_credentials(self):
        service = FreeLLMAPIService()
        with patch.object(service, '_listener_ports', return_value=[]):
            with self.assertRaises(FreeLLMAPIError): service.discover()

    def test_hash_mismatch_never_runs_installer(self):
        import io
        service = FreeLLMAPIService()
        with patch('blogpost.freellmapi.os.name', 'nt'), patch('blogpost.freellmapi.urlopen', return_value=io.BytesIO(b'not the official installer')), patch('blogpost.freellmapi.subprocess.run') as run:
            with self.assertRaisesRegex(FreeLLMAPIError, '校验失败'):
                service.install()
        run.assert_not_called()

    def test_setup_reuses_running_instance_without_installing(self):
        service = FreeLLMAPIService()
        with patch.object(service, 'is_installed', return_value=True), patch.object(service, 'discover', return_value=('http://127.0.0.1:31415/v1', 'key')), patch.object(service, 'install') as install, patch('blogpost.freellmapi.subprocess.Popen') as launch:
            self.assertEqual(service.prepare(False), ('http://127.0.0.1:31415/v1', 'key'))
        install.assert_not_called()
        launch.assert_not_called()

    def test_settings_window_automatically_configures_successful_service(self):
        import tempfile
        import time
        import tkinter as tk
        from pathlib import Path
        from types import SimpleNamespace
        from blogpost.secrets import DpapiSecretStore
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.theme import configure_theme
        with tempfile.TemporaryDirectory() as root:
            window = tk.Tk(); window.withdraw(); configure_theme(window)
            try:
                context = SimpleNamespace(config=AppConfig.for_data_dir(Path(root)), secrets=DpapiSecretStore(Path(root) / 'key.bin'))
                dialog = SettingsDialog(window, context, Mock())
                dialog._select('freellmapi')
                service = Mock(); service.is_installed.return_value = True
                service.prepare.return_value = ('http://127.0.0.1:31416/v1', 'unified-key')
                client = Mock(); client.complete.return_value = 'OK'
                with patch('blogpost.ui.model_settings_dialog.FreeLLMAPIService', return_value=service), patch('blogpost.ui.model_settings_dialog.OpenAICompatibleClient', return_value=client):
                    dialog._setup_freellmapi()
                    deadline = time.monotonic() + 3
                    while dialog._setup_running and time.monotonic() < deadline:
                        window.update(); time.sleep(0.02)
                    self.assertFalse(dialog._setup_running)
                    self.assertEqual(dialog.state.active_id, 'freellmapi')
                    self.assertEqual(dialog.values['base_url'].get(), 'http://127.0.0.1:31416/v1')
                    self.assertEqual(dialog.state.keys['freellmapi'], 'unified-key')
                    self.assertIn('请点击“保存设置”', dialog.status.get())
                dialog.destroy()
            finally:
                window.destroy()

    def test_start_failure_does_not_replace_active_connection(self):
        import tempfile
        import time
        import tkinter as tk
        from pathlib import Path
        from types import SimpleNamespace
        from blogpost.secrets import DpapiSecretStore
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.theme import configure_theme
        with tempfile.TemporaryDirectory() as root:
            window = tk.Tk(); window.withdraw(); configure_theme(window)
            try:
                context = SimpleNamespace(config=AppConfig.for_data_dir(Path(root)), secrets=DpapiSecretStore(Path(root) / 'key.bin'))
                dialog = SettingsDialog(window, context, Mock()); window.update(); dialog._select('freellmapi'); window.update()
                original = dialog.state.active_id
                service = Mock(); service.is_installed.return_value = True
                service.prepare.side_effect = FreeLLMAPIError('服务启动超时')
                with patch('blogpost.ui.model_settings_dialog.FreeLLMAPIService', return_value=service):
                    dialog._setup_freellmapi()
                    deadline = time.monotonic() + 3
                    while dialog._setup_running and time.monotonic() < deadline:
                        window.update(); time.sleep(0.02)
                self.assertEqual(dialog.state.active_id, original)
                self.assertIn('服务启动超时', dialog.status.get())
                dialog.destroy()
            finally:
                window.destroy()

    def test_model_failure_keeps_new_key_when_switching_pages(self):
        import tempfile
        import time
        import tkinter as tk
        from pathlib import Path
        from types import SimpleNamespace
        from blogpost.secrets import DpapiSecretStore
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.theme import configure_theme
        with tempfile.TemporaryDirectory() as root:
            window = tk.Tk(); window.withdraw(); configure_theme(window)
            try:
                context = SimpleNamespace(config=AppConfig.for_data_dir(Path(root)), secrets=DpapiSecretStore(Path(root) / 'key.bin'))
                dialog = SettingsDialog(window, context, Mock()); window.update(); dialog._select('freellmapi'); window.update()
                dialog.values['key'].set('old-key')
                service = Mock(); service.is_installed.return_value = True
                service.prepare.return_value = ('http://127.0.0.1:31416/v1', 'new-key')
                client = Mock(); client.complete.side_effect = ValueError('not ready')
                with patch('blogpost.ui.model_settings_dialog.FreeLLMAPIService', return_value=service), patch('blogpost.ui.model_settings_dialog.OpenAICompatibleClient', return_value=client):
                    dialog._setup_freellmapi()
                    deadline = time.monotonic() + 3
                    while dialog._setup_running and time.monotonic() < deadline:
                        window.update(); time.sleep(0.02)
                window.update()
                dialog._show_page('safety')
                window.update()
                self.assertEqual(dialog.state.keys['freellmapi'], 'new-key')
                dialog.destroy()
            finally:
                window.destroy()
