"""Reject invalid settings before the service accepts traffic."""

import os
import unittest
from unittest.mock import patch

from settings import Settings


class SettingsTests(unittest.TestCase):
    def test_environment_values_are_read_and_converted(self):
        with patch.dict(os.environ, {"GITHUB_TIMEOUT_SECONDS": "2.5",
                        "GITHUB_REQUEST_BUDGET_SECONDS": "12", "GITHUB_MAX_PAGES": "3",
                        "GITHUB_TOKEN": " token ", "LOG_LEVEL": "warning"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.timeout_seconds, 2.5)
        self.assertEqual(settings.request_budget_seconds, 12)
        self.assertEqual(settings.max_pages, 3)
        self.assertEqual(settings.github_token, "token")
        self.assertEqual(settings.log_level, "WARNING")
        self.assertNotIn("token", repr(settings))

    def test_invalid_numeric_settings_and_log_levels_fail_fast(self):
        cases = [(name, value) for name in ("GITHUB_TIMEOUT_SECONDS", "GITHUB_REQUEST_BUDGET_SECONDS")
                 for value in ("0", "-1", "nan", "inf", "not-a-number")]
        cases += [("GITHUB_MAX_PAGES", value) for value in ("0", "-1", "1.5", "abc")]
        cases += [("LOG_LEVEL", "not-a-level")]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                with patch.dict(os.environ, {name: value}, clear=True):
                    with self.assertRaises(ValueError):
                        Settings.from_env()

    def test_defaults_work_without_environment_variables(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env(), Settings())
