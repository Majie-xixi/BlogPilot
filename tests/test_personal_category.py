from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blogpost.domain import Article, RunStatus
from blogpost.publishers.cto51 import Cto51Publisher, OPEN_SETTINGS_SCRIPT
from blogpost.publishers.personal_categories import CategoryError


class PersonalCategoryTests(unittest.TestCase):
    def setUp(self):
        class Session:
            def __init__(self):
                self.commands = []
                self.personal_ok = False

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
                    return dict(categoryOk=True, secondaryOk=True, personalOk=self.personal_ok, originalOk=True, releaseReady=True)
                if "document.documentElement?.outerHTML" in expression:
                    return {"html": '<input id="selfType"><ul id="selfType_list"></ul>'}
                raise AssertionError("unexpected browser expression")

        self.session = Session()
        chrome = SimpleNamespace(
            ensure_running=lambda url: False,
            open_tab=lambda url: {"webSocketDebuggerUrl": "ws://test"},
        )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.publisher = Cto51Publisher(chrome, self.root, personal_category="工程实践")
        self.article = Article("标题", "# 标题", "主题")
        self.enterContext(patch("blogpost.publishers.cto51.CdpSession", return_value=self.session))
        self.enterContext(patch.object(Cto51Publisher, "_wait_editor_stable"))
        self.enterContext(patch.object(Cto51Publisher, "_fill_and_verify", return_value=dict(titleOk=True, bodyOk=True)))
        self.enterContext(patch.object(Cto51Publisher, "_wait_publish_dialog"))
        self.select = self.enterContext(patch.object(Cto51Publisher, "_select_personal_category", return_value=False))
        self.ensure = self.enterContext(patch("blogpost.publishers.cto51.ensure_personal_category", create=True))

    def test_missing_category_explains_create_and_refresh_without_publishing(self):
        result = self.publisher.publish(self.article, "AI 智能体", False)
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIn("工程实践", result.message)
        self.assertIn("创建", result.message)
        self.assertIn("刷新", result.message)
        self.assertEqual(self.session.commands, ["Page.enable"])
        self.assertEqual(len(list(self.root.glob("*.html"))), 1)

    def test_dry_run_ensures_category_then_selects_without_final_release(self):
        events = []
        self.ensure.side_effect = lambda client, name: events.append("ensure")
        self.select.side_effect = lambda session, name: events.append("select") or True
        result = self.publisher.publish(self.article, "AI 智能体", True)
        self.assertEqual(result.status, RunStatus.SKIPPED)
        self.assertEqual(events, ["ensure", "select"])
        self.assertEqual(self.ensure.call_args.args[1], "工程实践")
        self.assertEqual(self.session.commands, ["Page.enable"])
        self.assertEqual(list(self.root.glob("*.html")), [])

    def test_uncertain_creation_stops_before_selection_or_publication(self):
        self.ensure.side_effect = CategoryError("分类创建结果无法确认，不会重复创建")
        result = self.publisher.publish(self.article, "AI 智能体", False)
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIn("无法确认", result.message)
        self.select.assert_not_called()
        self.assertEqual(self.session.commands, ["Page.enable"])

    def test_already_selected_category_does_not_run_ensure(self):
        self.session.personal_ok = True
        result = self.publisher.publish(self.article, "AI 智能体", True)
        self.assertEqual(result.status, RunStatus.SKIPPED)
        self.ensure.assert_not_called()
        self.select.assert_not_called()


if __name__ == "__main__":
    unittest.main()
