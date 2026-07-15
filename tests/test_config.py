from datetime import time
from pathlib import Path
import unittest

from blogpost.config import AppConfig, ConfigError


class ConfigTests(unittest.TestCase):
    def test_defaults_match_the_confirmed_workflow(self):
        cfg = AppConfig()

        self.assertEqual(cfg.history_dir.name, "BlogPilot")
        self.assertEqual(cfg.generated_dir, cfg.history_dir / "generated_posts")
        self.assertEqual(cfg.schedule_time, time(10, 0))
        self.assertEqual(cfg.api_base_url, "https://api.deepseek.com")
        self.assertEqual(cfg.model, "deepseek-v4-pro")
        self.assertTrue(cfg.dry_run)

    def test_legacy_deepseek_defaults_are_migrated(self):
        cfg = AppConfig.from_json_dict(
            {
                "api_base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
            }
        )

        self.assertEqual(cfg.api_base_url, "https://api.deepseek.com")
        self.assertEqual(cfg.model, "deepseek-v4-pro")

    def test_config_rejects_generated_directory_outside_history(self):
        with self.assertRaisesRegex(ConfigError, "generated"):
            AppConfig(generated_dir=Path(r"E:\somewhere-else"))

    def test_config_requires_model_for_generation(self):
        cfg = AppConfig(model="")
        with self.assertRaisesRegex(ConfigError, "model"):
            cfg.validate_for_run()


if __name__ == "__main__":
    unittest.main()
