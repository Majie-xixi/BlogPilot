import unittest

from blogpost.ui.main_window import format_schedule_status


class ScheduleStatusUiTests(unittest.TestCase):
    def test_missing_task_requests_install(self):
        self.assertEqual(
            format_schedule_status("Missing", "10:00"),
            ("尚未安装", "配置时间 10:00 · 点击下方按钮安装"),
        )

    def test_missing_executable_requests_update(self):
        value, detail = format_schedule_status(
            "Invalid|ExecutableMissing",
            "10:00",
        )

        self.assertEqual(value, "任务需要更新")
        self.assertIn("启动文件不存在", detail)

    def test_action_mismatch_requests_update(self):
        value, detail = format_schedule_status(
            "Invalid|ActionMismatch",
            "10:00",
        )

        self.assertEqual(value, "任务需要更新")
        self.assertIn("启动命令已经过期", detail)

    def test_failed_task_shows_error_code(self):
        value, detail = format_schedule_status("Failed|2147942402", "10:00")

        self.assertEqual(value, "上次运行失败")
        self.assertIn("2147942402", detail)

    def test_ready_task_keeps_normal_schedule_copy(self):
        self.assertEqual(
            format_schedule_status("Ready", "10:00"),
            ("每天 10:00", "Windows 计划任务已安装 · 就绪"),
        )


if __name__ == "__main__":
    unittest.main()
