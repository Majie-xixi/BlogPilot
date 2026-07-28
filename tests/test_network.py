import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blogpost.network import internet_connection_status


class NetworkStatusTests(unittest.TestCase):
    def _result(self, stdout: str, returncode: int = 0):
        return SimpleNamespace(stdout=stdout, returncode=returncode)

    def test_windows_internet_access_is_online(self):
        with (
            patch("blogpost.network.os.name", "nt"),
            patch(
                "blogpost.network.subprocess.run",
                return_value=self._result("InternetAccess\r\n"),
            ),
        ):
            self.assertIs(internet_connection_status(), True)

    def test_windows_missing_profile_is_offline(self):
        with (
            patch("blogpost.network.os.name", "nt"),
            patch(
                "blogpost.network.subprocess.run",
                return_value=self._result("None\r\n"),
            ),
        ):
            self.assertIs(internet_connection_status(), False)

    def test_probe_failure_is_unknown_instead_of_false_offline(self):
        with (
            patch("blogpost.network.os.name", "nt"),
            patch(
                "blogpost.network.subprocess.run",
                return_value=self._result("", returncode=1),
            ),
        ):
            self.assertIsNone(internet_connection_status())

    @unittest.skipIf(os.name == "nt", "non-Windows behavior")
    def test_non_windows_is_unknown(self):
        self.assertIsNone(internet_connection_status())


if __name__ == "__main__":
    unittest.main()
