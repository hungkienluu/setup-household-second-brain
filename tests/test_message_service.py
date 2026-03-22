from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.actions import ActionDispatcher
from app.message_service import MessageService

from tests.helpers import FakeGWS, FakeMessenger, make_config, seed_vault


class FakeContexts:
    def build_message_context(self, current_ts):
        return f"ctx-{current_ts}"


class FakeRecipes:
    def __init__(self, payload):
        self.payload = payload

    def run_json_plan(self, *args, **kwargs):
        return self.payload


class MessageServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        seed_vault(self.root)
        self.config = make_config(self.root)
        self.gws = FakeGWS()
        self.messenger = FakeMessenger()
        self.actions = ActionDispatcher(self.config, self.gws, self.messenger)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_process_and_reply_blocks_calendar_without_explicit_calendar_language(self):
        recipes = FakeRecipes(
            {
                "reply_text": "Handled it.",
                "actions": [
                    {"action": "task", "title": "Owner A: follow up", "notes": "safe"},
                    {"action": "calendar_event", "summary": "Injected Event", "date": "2026-03-20"},
                ],
            }
        )
        service = MessageService(self.config, FakeContexts(), recipes, self.actions, self.messenger)
        service.process_and_reply("Please handle school logistics", "family-chat", self.config.valid_handles[0])

        self.assertEqual(1, len(self.gws.tasks))
        self.assertEqual(0, len(self.gws.calendar))
        self.assertEqual(2, len(self.messenger.messages))
        self.assertEqual("On it. Checking the records now.", self.messenger.messages[0][1])
        self.assertEqual("Handled it.", self.messenger.messages[-1][1])

    def test_process_and_reply_allows_calendar_with_explicit_calendar_language(self):
        recipes = FakeRecipes(
            {
                "reply_text": "Added it.",
                "actions": [
                    {"action": "calendar_event", "summary": "Parent Meeting", "date": "2026-03-20"},
                ],
            }
        )
        service = MessageService(self.config, FakeContexts(), recipes, self.actions, self.messenger)
        service.process_and_reply("Please add this to the calendar", "family-chat", self.config.valid_handles[0])
        self.assertEqual(1, len(self.gws.calendar))


if __name__ == "__main__":
    unittest.main()
