import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from pathlib import Path

from blogpost.config import AppConfig, ConfigError, ModelConnection
from blogpost.llm.client import LlmError, OpenAICompatibleClient
from blogpost.llm.codex import CodexClient


class ProxyTests(unittest.TestCase):
    def test_save_rejects_proxy_credentials_without_changing_existing_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text('{}', encoding='utf-8')
            config = AppConfig(connections=[ModelConnection('c', 'C', 'codex', proxy_mode='manual', proxy_url='http://user:pass@127.0.0.1:8080')], active_connection_id='c')
            with self.assertRaises(ConfigError):
                config.save(path)
            self.assertEqual(path.read_text(encoding='utf-8'), '{}')
    def test_https_requests_use_proxy_connect_tunnel(self):
        tunnels = []
        class Handler(BaseHTTPRequestHandler):
            def do_CONNECT(self):
                tunnels.append(self.path)
                self.send_error(502)
            def log_message(self, *args):
                pass
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as proxy:
            thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            thread.start()
            try:
                client = OpenAICompatibleClient('https://example.invalid/v1', 'm', 'key', max_retries=0,
                                                proxy_mode='manual', proxy_url=f'http://127.0.0.1:{proxy.server_port}')
                with self.assertRaises(LlmError):
                    client.complete([])
                self.assertEqual(tunnels, ['example.invalid:443'])
            finally:
                proxy.shutdown()
                thread.join(timeout=5)

    def test_old_connection_defaults_to_environment(self):
        config = AppConfig.from_json_dict({'connections': [{'id': 'c', 'name': 'C', 'kind': 'codex'}], 'active_connection_id': 'c'})
        self.assertEqual(config.current_connection().proxy_mode, 'environment')

    def test_invalid_or_credentialed_proxy_rejected(self):
        for url in ('socks5://127.0.0.1:1080', 'http://user:pass@127.0.0.1:8080', 'http://example:99999', 'http://host/path', ''):
            config = AppConfig(connections=[ModelConnection('c', 'C', 'codex', proxy_mode='manual', proxy_url=url)], active_connection_id='c')
            with self.subTest(url=url), self.assertRaises(ConfigError):
                config.validate_for_run()

    def test_manual_http_proxy_and_direct_use_separate_routes(self):
        hits = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append((self.server.server_port, self.path))
                self.rfile.read(int(self.headers['Content-Length']))
                body = json.dumps({'choices': [{'message': {'content': 'OK'}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as target, ThreadingHTTPServer(('127.0.0.1', 0), Handler) as proxy:
            threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (target, proxy)]
            for thread in threads:
                thread.start()
            try:
                base = f'http://127.0.0.1:{target.server_port}/v1'
                proxy_url = f'http://127.0.0.1:{proxy.server_port}'
                with patch.dict(os.environ, {'HTTP_PROXY': proxy_url, 'http_proxy': proxy_url, 'NO_PROXY': '*', 'no_proxy': '*'}):
                    self.assertEqual(OpenAICompatibleClient(base, 'm', 'key', proxy_mode='manual', proxy_url=proxy_url).complete([]), 'OK')
                    with patch.dict(os.environ, {'NO_PROXY': '', 'no_proxy': ''}):
                        self.assertEqual(OpenAICompatibleClient(base, 'm', 'key', proxy_mode='direct').complete([]), 'OK')
                        with patch('urllib.request._opener', None):
                            self.assertEqual(OpenAICompatibleClient(base, 'm', 'key').complete([]), 'OK')
                self.assertEqual([port for port, _ in hits], [proxy.server_port, target.server_port, proxy.server_port])
            finally:
                target.shutdown()
                proxy.shutdown()
                for thread in threads:
                    thread.join(timeout=5)

    @patch('blogpost.llm.codex.subprocess.run')
    def test_codex_manual_proxy_is_scoped_to_child_process(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout='OK', stderr='')
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://old:1', 'NO_PROXY': '*'}):
            self.assertEqual(CodexClient(proxy_mode='manual', proxy_url='http://127.0.0.1:7890').complete([]), 'OK')
            env = run.call_args.kwargs['env']
            self.assertEqual(env['HTTPS_PROXY'], 'http://127.0.0.1:7890')
            self.assertEqual(env['NO_PROXY'], '')
            self.assertEqual(os.environ['HTTPS_PROXY'], 'http://old:1')

    @patch('blogpost.llm.codex.subprocess.run')
    def test_codex_direct_does_not_inherit_proxy(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout='OK', stderr='')
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://old:1', 'ALL_PROXY': 'http://old:1'}):
            CodexClient(proxy_mode='direct').complete([])
            env = run.call_args.kwargs['env']
            self.assertNotIn('HTTPS_PROXY', env)
            self.assertNotIn('ALL_PROXY', env)
            self.assertEqual(env['NO_PROXY'], '*')
