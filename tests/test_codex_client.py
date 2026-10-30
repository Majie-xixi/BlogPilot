import subprocess
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blogpost.llm.client import LlmError
from blogpost.llm.codex import CodexClient, find_codex


class CodexClientTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows desktop installation')
    def test_desktop_codex_is_used_when_missing_from_path(self):
        with tempfile.TemporaryDirectory(dir='.') as root:
            executable = Path(root) / 'OpenAI' / 'Codex' / 'bin' / 'version' / 'codex.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict(os.environ, {'LOCALAPPDATA': str(Path(root).resolve()), 'PATH': ''}):
                with patch('blogpost.llm.codex.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout='OK', stderr='')) as run:
                    self.assertEqual(CodexClient().complete([{'role': 'user', 'content': 'hello'}]), 'OK')
                    self.assertEqual(Path(run.call_args.args[0][0]), executable.resolve())

    @unittest.skipUnless(os.name == 'nt', 'Windows desktop installation')
    def test_latest_desktop_binary_is_used_and_path_takes_priority(self):
        with tempfile.TemporaryDirectory(dir='.') as root:
            bin_dir = Path(root).resolve() / 'OpenAI' / 'Codex' / 'bin'
            older = bin_dir / 'old' / 'codex.exe'
            newer = bin_dir / 'new' / 'codex.exe'
            for executable in (older, newer):
                executable.parent.mkdir(parents=True)
                executable.touch()
            os.utime(older, (1000000000, 1000000000))
            os.utime(newer, (1100000000, 1100000000))
            with patch.dict(os.environ, {'LOCALAPPDATA': str(Path(root).resolve()), 'PATH': ''}):
                self.assertEqual(find_codex(), str(newer))
                with patch('blogpost.llm.codex.shutil.which', return_value='C:\\custom\\codex.exe'):
                    self.assertEqual(find_codex(), 'C:\\custom\\codex.exe')

    @patch('blogpost.llm.codex.subprocess.run')
    def test_optional_model_is_passed_to_codex(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout='OK', stderr='')
        CodexClient(model='test-model').complete([{'role': 'user', 'content': 'hello'}])
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--model') + 1], 'test-model')

    @patch("blogpost.llm.codex.subprocess.run")
    def test_completion_passes_prompt_via_stdin_and_returns_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout='{"ok": true}\n', stderr='')
        client = CodexClient()
        self.assertEqual(client.complete([{"role": "user", "content": "中文选题"}], json_mode=True), '{"ok": true}')
        args, kwargs = run.call_args
        self.assertIn('--ephemeral', args[0])
        self.assertIn('read-only', args[0])
        self.assertNotIn('中文选题', ' '.join(args[0]))
        self.assertIn('中文选题', kwargs['input'])

    @patch("blogpost.llm.codex.subprocess.run")
    def test_failure_does_not_expose_cli_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, stdout='', stderr='secret diagnostic')
        with self.assertRaises(LlmError) as caught:
            CodexClient().complete([{"role": "user", "content": "x"}])
        self.assertNotIn('secret diagnostic', str(caught.exception))

    @patch("blogpost.llm.codex.subprocess.run", side_effect=FileNotFoundError())
    def test_missing_codex_is_reported(self, run):
        with self.assertRaisesRegex(LlmError, 'Codex'):
            CodexClient().complete([])

    @patch("blogpost.llm.codex.subprocess.run", side_effect=subprocess.TimeoutExpired('codex', 1))
    def test_timeout_is_reported(self, run):
        with self.assertRaisesRegex(LlmError, '超时'):
            CodexClient().complete([])

    @patch("blogpost.llm.codex.subprocess.run")
    def test_empty_response_is_an_error(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout='  ', stderr='')
        with self.assertRaises(LlmError):
            CodexClient().complete([])


class CodexConfigTests(unittest.TestCase):
    @patch('blogpost.application.PublishingPipeline')
    @patch('blogpost.application.app_data_dir')
    def test_pipeline_uses_active_connection_proxy(self, data_dir, pipeline):
        from pathlib import Path
        from blogpost.application import ApplicationContext
        from blogpost.config import AppConfig, ModelConnection
        data_dir.return_value = Path('.')
        cfg = AppConfig(connections=[ModelConnection('codex', 'Codex', 'codex', proxy_mode='manual', proxy_url='http://127.0.0.1:7890')], active_connection_id='codex')
        account = SimpleNamespace(enabled=True, article_subdir='default', schedule_time=cfg.schedule_time,
                                  category='', profile_url='', article_type='', content_directions='', keywords='',
                                  secondary_category='', personal_category='')
        repository = Mock(); repository.get_account.return_value = account
        ApplicationContext(cfg, repository, Mock(), Mock(), Mock(), Mock()).build_pipeline()
        client = pipeline.call_args.args[3].client
        self.assertEqual((client.proxy_mode, client.proxy_url), ('manual', 'http://127.0.0.1:7890'))

    @patch('blogpost.application.PublishingPipeline')
    @patch('blogpost.application.app_data_dir')
    def test_pipeline_uses_explicit_codex_model(self, data_dir, pipeline):
        from pathlib import Path
        from blogpost.application import ApplicationContext
        from blogpost.config import AppConfig, ModelConnection
        data_dir.return_value = Path('.')
        cfg = AppConfig(connections=[ModelConnection('codex', 'Codex', 'codex', model='selected-model')], active_connection_id='codex')
        account = SimpleNamespace(enabled=True, article_subdir='default', schedule_time=cfg.schedule_time, category='', profile_url='', article_type='', content_directions='', keywords='', secondary_category='', personal_category='')
        repository = Mock(); repository.get_account.return_value = account
        ApplicationContext(cfg, repository, Mock(), Mock(), Mock(), Mock()).build_pipeline()
        self.assertEqual(pipeline.call_args.args[3].client.model, 'selected-model')

    def test_codex_does_not_require_api_configuration_and_round_trips(self):
        from blogpost.config import AppConfig
        cfg = AppConfig(provider='codex', api_base_url='', model='')
        cfg.validate_for_run()
        self.assertEqual(AppConfig.from_json_dict(cfg.to_json_dict()).provider, 'codex')

    def test_unknown_provider_is_rejected(self):
        from blogpost.config import AppConfig, ConfigError
        with self.assertRaises(ConfigError):
            AppConfig(provider='unknown').validate_for_run()

    @patch('blogpost.application.PublishingPipeline')
    @patch('blogpost.application.app_data_dir')
    def test_pipeline_selects_codex_without_reading_api_key(self, data_dir, pipeline):
        from pathlib import Path
        from blogpost.application import ApplicationContext
        from blogpost.config import AppConfig

        data_dir.return_value = Path('.')
        cfg = AppConfig(provider='codex')
        account = SimpleNamespace(enabled=True, article_subdir='default', schedule_time=cfg.schedule_time,
                                  category='', profile_url='', article_type='', content_directions='', keywords='',
                                  secondary_category='', personal_category='')
        repository = Mock()
        repository.get_account.return_value = account
        secrets = Mock()
        context = ApplicationContext(cfg, repository, secrets, Mock(), Mock(), Mock())
        context.build_pipeline()
        secrets.get_api_key.assert_not_called()
        self.assertIsInstance(pipeline.call_args.args[3].client, CodexClient)
