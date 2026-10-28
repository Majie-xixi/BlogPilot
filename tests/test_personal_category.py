from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blogpost.domain import Article, RunStatus
from blogpost.publishers.cto51 import Cto51Publisher, OPEN_SETTINGS_SCRIPT


class PersonalCategoryTests(unittest.TestCase):
    def test_missing_category_explains_create_and_refresh_without_publishing(self):
        class Session:
            def __init__(self):
                self.commands = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def command(self, method, *args):
                self.commands.append(method)

            def evaluate(self, expression):
                if "login:location.href" in expression:
                    return {"login": False, "challenge": False}
                if expression == OPEN_SETTINGS_SCRIPT:
                    return True
                if "personalValue:" in expression:
                    return dict(categoryOk=True, secondaryOk=True, personalOk=False, originalOk=True, releaseReady=True)
                if "document.documentElement?.outerHTML" in expression:
                    return {"html": '<input id="selfType"><ul id="selfType_list"></ul>'}
                raise AssertionError("unexpected browser expression")

        session = Session()
        chrome = SimpleNamespace(
            ensure_running=lambda url: False,
            open_tab=lambda url: {"webSocketDebuggerUrl": "ws://test"},
        )
        with tempfile.TemporaryDirectory() as root:
            publisher = Cto51Publisher(chrome, Path(root), personal_category="工程实践")
            with (
                patch("blogpost.publishers.cto51.CdpSession", return_value=session),
                patch.object(Cto51Publisher, "_wait_editor_stable"),
                patch.object(Cto51Publisher, "_fill_and_verify", return_value=dict(titleOk=True, bodyOk=True)),
                patch.object(Cto51Publisher, "_wait_publish_dialog"),
                patch.object(Cto51Publisher, "_select_personal_category", return_value=False),
            ):
                result = publisher.publish(Article("标题", "# 标题", "主题"), "AI 智能体", False)

            self.assertEqual(result.status, RunStatus.FAILED)
            self.assertIn("工程实践", result.message)
            self.assertIn("创建", result.message)
            self.assertIn("刷新", result.message)
            self.assertEqual(session.commands, ["Page.enable"])
            self.assertEqual(len(list(Path(root).glob("*.html"))), 1)


if __name__ == "__main__":
    unittest.main()
