import logging
import unittest

from blogpost.logging_setup import RedactingFilter


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


if __name__ == "__main__":
    unittest.main()
