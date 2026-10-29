import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from blogpost.config import AppConfig, ModelConnection
from blogpost.secrets import DpapiSecretStore


class ModelConnectionTests(unittest.TestCase):
    def test_legacy_configuration_becomes_two_connections_without_losing_values(self):
        cfg = AppConfig.from_json_dict({'provider': 'codex', 'api_base_url': 'https://example.test/v1', 'model': 'custom', 'dry_run': False})
        self.assertEqual(cfg.current_connection().kind, 'codex')
        api = next(c for c in cfg.connections if c.id == 'legacy-api')
        self.assertEqual((api.base_url, api.model), ('https://example.test/v1', 'custom'))
        self.assertFalse(cfg.dry_run)
        self.assertEqual(AppConfig.from_json_dict(cfg.to_json_dict()).connections, cfg.connections)

    def test_connections_have_separate_keys_and_legacy_env_is_scoped(self):
        with tempfile.TemporaryDirectory() as root:
            store = DpapiSecretStore(Path(root) / 'api-key.bin')
            store.set_api_key('first', 'legacy-api')
            store.set_api_key('second', 'other')
            with patch.dict(os.environ, {'BLOGPOST_API_KEY': 'environment'}):
                self.assertEqual(store.get_api_key('legacy-api'), 'environment')
                self.assertEqual(store.get_api_key('other'), 'second')
            self.assertEqual(store.get_api_key('legacy-api'), 'first')

    def test_rejects_missing_active_connection(self):
        cfg = AppConfig(connections=[ModelConnection('one', 'DeepSeek', 'api', 'DeepSeek', 'https://example.test', 'model')], active_connection_id='missing')
        with self.assertRaises(ValueError):
            cfg.validate_for_run()

    def test_unknown_legacy_provider_is_not_silently_changed(self):
        with self.assertRaises(ValueError):
            AppConfig.from_json_dict({'provider': 'unexpected'})

    def test_deleting_connection_is_draft_only_and_active_connection_is_protected(self):
        from blogpost.ui.settings_state import SettingsState
        cfg = AppConfig.from_json_dict({'provider': 'codex'})
        state = SettingsState(cfg)
        with self.assertRaises(ValueError):
            state.remove_connection('codex')
        state.remove_connection('legacy-api')
        self.assertEqual([c.id for c in state.connections], ['codex'])
        self.assertEqual(len(cfg.connections), 2)
        self.assertEqual(state.deleted_ids, {'legacy-api'})

    def test_delete_new_connection_discards_draft_key_without_requesting_disk_delete(self):
        from blogpost.ui.settings_state import SettingsState
        state = SettingsState(AppConfig())
        state.connections.append(ModelConnection('new', '新连接', 'api'))
        state.keys['new'] = 'not-saved'
        state.remove_connection('new')
        self.assertNotIn('new', state.keys)
        self.assertNotIn('new', state.deleted_ids)

    def test_delete_saved_key_is_rolled_back_if_config_save_fails(self):
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.settings_state import SettingsState
        with tempfile.TemporaryDirectory() as root:
            store = DpapiSecretStore(Path(root) / 'api-key.bin')
            store.set_api_key('old-key')
            state = SettingsState(AppConfig.from_json_dict({'provider': 'codex'}))
            state.remove_connection('legacy-api')
            dialog = SimpleNamespace(state=state, context=SimpleNamespace(secrets=store), dry_run=Mock(get=Mock(return_value=True)), _capture=Mock(), on_saved=Mock(), destroy=Mock())
            with patch('blogpost.ui.model_settings_dialog.config_path', return_value=Path(root) / 'config.json'), patch.object(AppConfig, 'save', side_effect=OSError('failed')), patch('blogpost.ui.model_settings_dialog.messagebox.showerror'):
                SettingsDialog._save(dialog)
            self.assertEqual(store.get_api_key(), 'old-key')

    def test_delete_saved_connection_removes_key_and_keeps_encrypted_backup(self):
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.settings_state import SettingsState
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            store = DpapiSecretStore(root / 'api-key.bin')
            store.set_api_key('old-key')
            state = SettingsState(AppConfig.from_json_dict({'provider': 'codex'}))
            state.remove_connection('legacy-api')
            dialog = SimpleNamespace(state=state, context=SimpleNamespace(secrets=store), dry_run=Mock(get=Mock(return_value=True)), _capture=Mock(), on_saved=Mock(), destroy=Mock())
            with patch('blogpost.ui.model_settings_dialog.config_path', return_value=root / 'config.json'), patch('blogpost.ui.model_settings_dialog.messagebox.showerror') as error:
                SettingsDialog._save(dialog)
                error.assert_not_called()
            self.assertIsNone(store.get_api_key())
            backups = list(root.glob('api-key.bin.deleted-*.bak'))
            self.assertEqual(len(backups), 1)
            self.assertNotIn(b'old-key', backups[0].read_bytes())
            self.assertEqual([c.id for c in AppConfig.load(root / 'config.json').connections], ['codex'])

    def test_compatible_local_gateway_receives_chat_completions_and_json_mode(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from blogpost.llm.client import OpenAICompatibleClient
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body = json.dumps({'choices': [{'message': {'content': '{"ok": true}'}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = OpenAICompatibleClient(f'http://127.0.0.1:{server.server_port}/v1', 'auto', 'fixture-key')
            self.assertEqual(client.complete([{'role': 'user', 'content': 'test'}], json_mode=True), '{"ok": true}')
            self.assertEqual(received[0][0], '/v1/chat/completions')
            self.assertEqual(received[0][1], 'Bearer fixture-key')
            self.assertEqual(received[0][2]['response_format'], {'type': 'json_object'})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @patch('blogpost.application.PublishingPipeline')
    @patch('blogpost.application.app_data_dir', return_value=Path('.'))
    def test_pipeline_uses_active_connection_and_its_key(self, data_dir, pipeline):
        from blogpost.application import ApplicationContext
        cfg = AppConfig(connections=[ModelConnection('other', 'OpenAI', 'api', 'OpenAI', 'https://example.test/v1', 'model-b')], active_connection_id='other')
        account = SimpleNamespace(enabled=True, article_subdir='default', schedule_time=cfg.schedule_time, category='', profile_url='', article_type='', content_directions='', keywords='', secondary_category='', personal_category='')
        repository = Mock(); repository.get_account.return_value = account
        secrets = Mock(); secrets.get_api_key.return_value = 'key-b'
        ApplicationContext(cfg, repository, secrets, Mock(), Mock(), Mock()).build_pipeline()
        secrets.get_api_key.assert_called_once_with('other')
        client = pipeline.call_args.args[3].client
        self.assertEqual((client.base_url, client.model, client.api_key), ('https://example.test/v1', 'model-b', 'key-b'))

    @patch('blogpost.application.PublishingPipeline')
    @patch('blogpost.application.app_data_dir', return_value=Path('.'))
    def test_pipeline_uses_codex_without_accessing_api_keys(self, data_dir, pipeline):
        from blogpost.application import ApplicationContext
        from blogpost.llm.codex import CodexClient
        cfg = AppConfig.from_json_dict({'provider': 'codex'})
        account = SimpleNamespace(enabled=True, article_subdir='default', schedule_time=cfg.schedule_time, category='', profile_url='', article_type='', content_directions='', keywords='', secondary_category='', personal_category='')
        repository = Mock(); repository.get_account.return_value = account
        secrets = Mock()
        ApplicationContext(cfg, repository, secrets, Mock(), Mock(), Mock()).build_pipeline()
        secrets.get_api_key.assert_not_called()
        self.assertIsInstance(pipeline.call_args.args[3].client, CodexClient)

    def test_settings_save_preserves_all_connections_and_global_safety(self):
        from blogpost.ui.settings_state import SettingsState
        cfg = AppConfig.from_json_dict({'provider': 'codex', 'dry_run': True})
        state = SettingsState(cfg)
        state.connections[0].model = 'changed-model'
        state.active_id = state.connections[0].id
        state.dry_run = False
        updated = state.configuration()
        self.assertEqual(len(updated.connections), 2)
        self.assertEqual(updated.current_connection().model, 'changed-model')
        self.assertFalse(updated.dry_run)
        self.assertEqual(cfg.connections[0].model, 'deepseek-v4-pro')

    def test_invalid_active_connection_cannot_be_saved(self):
        from blogpost.ui.settings_state import SettingsState
        cfg = AppConfig.from_json_dict({'provider': 'codex'})
        state = SettingsState(cfg)
        state.active_id = 'legacy-api'
        state.connections[0].base_url = ''
        with self.assertRaises(ValueError):
            state.configuration()

    def test_save_migrates_config_with_backup_and_preserves_legacy_key(self):
        import json
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.settings_state import SettingsState
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            legacy = {'provider': 'api', 'api_base_url': 'https://example.test/v1', 'model': 'model', 'dry_run': True}
            path.write_text(json.dumps(legacy), encoding='utf-8')
            store = DpapiSecretStore(Path(root) / 'api-key.bin')
            store.set_api_key('old-key')
            state = SettingsState(AppConfig.from_json_dict(legacy))
            state.keys['legacy-api'] = 'new-key'
            dialog = SimpleNamespace(state=state, context=SimpleNamespace(secrets=store), dry_run=Mock(get=Mock(return_value=False)), _capture=Mock(), on_saved=Mock(), destroy=Mock())
            with patch('blogpost.ui.model_settings_dialog.config_path', return_value=path), patch('blogpost.ui.model_settings_dialog.messagebox.showerror') as error:
                SettingsDialog._save(dialog)
                error.assert_not_called()
            self.assertEqual(json.loads(path.with_suffix('.json.pre-model-connections.bak').read_text(encoding='utf-8')), legacy)
            self.assertTrue((Path(root) / 'api-key.bin.pre-model-connections.bak').exists())
            self.assertEqual(store.get_api_key(), 'new-key')
            self.assertEqual(AppConfig.load(path).current_connection().model, 'model')
            self.assertFalse(AppConfig.load(path).dry_run)

    def test_failed_config_save_restores_previous_key(self):
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.settings_state import SettingsState
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            store = DpapiSecretStore(Path(root) / 'api-key.bin')
            store.set_api_key('old-key')
            state = SettingsState(AppConfig())
            state.keys['legacy-api'] = 'new-key'
            dialog = SimpleNamespace(state=state, context=SimpleNamespace(secrets=store), dry_run=Mock(get=Mock(return_value=True)), _capture=Mock(), on_saved=Mock(), destroy=Mock())
            with patch('blogpost.ui.model_settings_dialog.config_path', return_value=path), patch.object(AppConfig, 'save', side_effect=OSError('failed')), patch('blogpost.ui.model_settings_dialog.messagebox.showerror') as error:
                SettingsDialog._save(dialog)
                error.assert_called_once()
            self.assertEqual(store.get_api_key(), 'old-key')
            dialog.on_saved.assert_not_called()

    def test_settings_window_switches_connections_and_preserves_safety(self):
        import tkinter as tk
        import time
        from blogpost.ui.model_settings_dialog import SettingsDialog
        from blogpost.ui.theme import configure_theme
        with tempfile.TemporaryDirectory() as root:
            window = tk.Tk()
            window.withdraw()
            configure_theme(window)
            callback_errors = []
            window.report_callback_exception = lambda *error: callback_errors.append(error)
            try:
                cfg = AppConfig.for_data_dir(Path(root))
                context = SimpleNamespace(config=cfg, secrets=DpapiSecretStore(Path(root) / 'api-key.bin'))
                dialog = SettingsDialog(window, context, Mock())
                window.update()
                dialog.values['model'].set('custom-model')
                dialog._show_page('safety')
                self.assertEqual(dialog.safety_label.get(), '安全试运行：已开启')
                dialog.dry_run.set(False)
                self.assertEqual(dialog.safety_label.get(), '安全试运行：已关闭')
                dialog._show_page('model')
                self.assertEqual(dialog.values['model'].get(), 'custom-model')
                self.assertFalse(dialog.dry_run.get())
                dialog._add()
                draft_id = dialog.selected_id
                with patch('blogpost.ui.model_settings_dialog.messagebox.askyesno', return_value=False):
                    dialog._delete()
                self.assertTrue(any(c.id == draft_id for c in dialog.state.connections))
                with patch('blogpost.ui.model_settings_dialog.messagebox.askyesno', return_value=True):
                    dialog._delete()
                self.assertFalse(any(c.id == draft_id for c in dialog.state.connections))
                dialog._add()
                dialog.values['name'].set('OpenAI')
                dialog.values['base_url'].set('https://example.test/v1')
                dialog.values['model'].set('example')
                dialog.values['key'].set('example-key')
                client = Mock()
                with patch('blogpost.ui.model_settings_dialog.OpenAICompatibleClient', return_value=client) as client_type:
                    dialog._test()
                    deadline = time.monotonic() + 3
                    while dialog.status.get() == '正在测试连接…' and time.monotonic() < deadline:
                        window.update()
                        time.sleep(0.02)
                    self.assertEqual(dialog.status.get(), '连接测试成功')
                    client_type.assert_called_once_with('https://example.test/v1', 'example', 'example-key', timeout=20, max_retries=0)
                    client.complete.assert_called_once()
                dialog._activate()
                self.assertEqual(dialog.state.active_id, dialog.selected_id)
                self.assertEqual(len(dialog.state.connections), 3)
                with patch('blogpost.ui.model_settings_dialog.config_path', return_value=Path(root) / 'config.json'), patch('blogpost.ui.model_settings_dialog.messagebox.showerror') as error:
                    dialog._save()
                    error.assert_not_called()
                saved = AppConfig.load(Path(root) / 'config.json')
                self.assertEqual(saved.current_connection().name, 'OpenAI')
                self.assertFalse(saved.dry_run)
                self.assertEqual(context.secrets.get_api_key(saved.active_connection_id), 'example-key')
                window.update()
                self.assertEqual(callback_errors, [])
            finally:
                window.destroy()


if __name__ == '__main__':
    unittest.main()
