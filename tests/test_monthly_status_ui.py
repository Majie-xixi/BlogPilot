from datetime import datetime
import unittest

from blogpost.ui.main_window import format_monthly_status, resolve_today_status


class MonthlyStatusUiTests(unittest.TestCase):
    def test_online_month_count_shows_remaining_target(self):
        self.assertEqual(
            format_monthly_status(18, 21),
            "本月 18/21 篇 · 还差 3 篇",
        )

    def test_cached_online_count_is_clearly_labeled(self):
        self.assertEqual(
            format_monthly_status(
                18,
                21,
                checked_at=datetime(2026, 7, 28, 10, 0),
                online_error=True,
            ),
            "无法连接 51CTO · 上次在线统计 18/21 篇 · 还差 3 篇",
        )

    def test_unknown_month_count_never_uses_local_days(self):
        text = format_monthly_status(None, 21, online_error=True)

        self.assertEqual(text, "无法连接 51CTO · 请检查网络后重试")
        self.assertNotIn("本地", text)
        self.assertNotIn("7", text)

    def test_connected_but_unparsed_count_is_explicit(self):
        self.assertEqual(
            format_monthly_status(None, 21),
            "51CTO 已连接 · 月度统计暂未识别",
        )

    def test_successful_local_publish_is_not_downgraded_by_online_delay(self):
        self.assertEqual(
            resolve_today_status(
                local_published=True,
                online_published=False,
            ),
            "已发布",
        )

    def test_online_result_still_drives_status_without_local_record(self):
        self.assertEqual(
            resolve_today_status(
                local_published=False,
                online_published=True,
            ),
            "已发布",
        )
        self.assertEqual(
            resolve_today_status(
                local_published=False,
                online_published=False,
            ),
            "尚未发布",
        )


if __name__ == "__main__":
    unittest.main()
