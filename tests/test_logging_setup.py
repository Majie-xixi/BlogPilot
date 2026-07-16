import logging
import unittest

from blogpost.logging_setup import RedactingFilter
from blogpost.ui.main_window import parse_persisted_log_line


class LoggingTests(unittest.TestCase):
    def test_redacting_filter_hides_secrets(self):
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "Authorization: Bearer super-secret Cookie: token=abc api_key=sk-test-value",
            (),
            None,
        )

        RedactingFilter().filter(record)

        message = record.getMessage()
        self.assertNotIn("super-secret", message)
        self.assertNotIn("abc", message)
        self.assertNotIn("sk-test-value", message)
        self.assertIn("[REDACTED]", message)

    def test_persisted_pipeline_log_is_rendered_like_live_log(self):
        time_text, level, message = parse_persisted_log_line(
            "2026-07-16T08:38:41 INFO blogpost.pipeline "
            "pipeline status=skipped message=51CTO 线上显示今天已经发布"
        )
        self.assertEqual(time_text, "08:38:41")
        self.assertEqual(level, "success")
        self.assertIn("51CTO", message)

    def test_failed_persisted_log_uses_error_badge(self):
        _, level, message = parse_persisted_log_line(
            "2026-07-15T17:14:45 INFO blogpost.pipeline "
            "pipeline status=failed message=页面结构未识别"
        )
        self.assertEqual(level, "error")
        self.assertIn("执行失败", message)


if __name__ == "__main__":
    unittest.main()
