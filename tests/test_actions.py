from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.actions import ActionDispatcher

from tests.helpers import FakeGWS, FakeMessenger, make_config, seed_vault


class ActionDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        seed_vault(self.root)
        self.config = make_config(self.root)
        self.gws = FakeGWS()
        self.messenger = FakeMessenger()
        self.dispatcher = ActionDispatcher(self.config, self.gws, self.messenger)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_school_calendar_event_uses_timed_payload_when_time_present(self):
        self.dispatcher.execute_scheduled_actions(
            [
                {
                    "action": "school_calendar_event",
                    "title": "Spring Concert",
                    "date": "2026-03-22",
                    "start_time": "18:00",
                    "notes": "Gym",
                }
            ],
            {"school_calendar_event"},
        )
        self.assertEqual(1, len(self.gws.calendar))
        payload = self.gws.calendar[0]
        self.assertEqual("School: Spring Concert", payload["summary"])
        self.assertEqual("2026-03-22T18:00:00", payload["start"]["dateTime"])
        self.assertEqual("2026-03-22T19:00:00", payload["end"]["dateTime"])

    def test_blocked_file_append_does_not_abort_following_actions(self):
        self.dispatcher.execute_scheduled_actions(
            [
                {"action": "file_append", "path": "scripts/evil.py", "content": "oops"},
                {"action": "task", "title": "Owner A: real task", "notes": "safe"},
            ],
            {"file_append", "task"},
        )
        self.assertEqual(1, len(self.gws.tasks))
        self.assertEqual("Owner A: real task", self.gws.tasks[0]["title"])


if __name__ == "__main__":
    unittest.main()
