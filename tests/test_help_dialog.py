import unittest

from blogpost.ui.help_dialog import BUTTON_GUIDE, HELP_STEPS


class HelpContentTests(unittest.TestCase):
    def test_help_steps_cover_first_successful_publish(self):
        combined = " ".join(
            f"{step.title} {step.description}" for step in HELP_STEPS
        )

        for term in (
            "数据目录",
            "API Key",
            "账号管理",
            "自动发布登录",
            "安全试运行",
            "每日任务",
        ):
            self.assertIn(term, combined)

    def test_button_guide_preserves_all_main_actions(self):
        labels = {item.label for item in BUTTON_GUIDE}

        self.assertTrue(
            {
                "打开 51CTO",
                "自动发布登录",
                "更新每日任务",
                "打开最近文章",
                "打开文章目录",
                "重新发布最近文章",
            }.issubset(labels)
        )

    def test_help_content_never_asks_for_51cto_password(self):
        combined = " ".join(
            [
                *(step.description for step in HELP_STEPS),
                *(item.description for item in BUTTON_GUIDE),
            ]
        )

        self.assertNotIn("填写 51CTO 密码", combined)
        self.assertNotIn("存储 51CTO 密码", combined)
        self.assertIn("不会保存 51CTO 密码", combined)


if __name__ == "__main__":
    unittest.main()
