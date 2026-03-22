from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.recipe_runner import RecipeRunner

from tests.helpers import FakeGemini, make_config, seed_vault


class RecipeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        seed_vault(self.root)
        self.config = make_config(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_markdown_recipe_extracts_message_body_and_actions(self):
        gemini = FakeGemini(
            "[MESSAGE]\nHello family\n\n```json\n[{\"action\": \"task\", \"title\": \"Owner A: do thing\"}]\n```"
        )
        runner = RecipeRunner(self.config, gemini)
        output_file = self.root / "Briefs" / "daily" / "2026-03-20.md"
        result = runner.run_markdown_recipe(
            "imessage-checkin.yaml",
            "ctx",
            {"vault_path": str(self.root)},
            model="flash",
            approval_mode="plan",
            output_file=output_file,
        )
        self.assertEqual("Hello family", result.content)
        self.assertEqual("task", result.actions[0]["action"])
        self.assertEqual("Hello family", output_file.read_text())

    def test_markdown_recipe_strips_preamble_before_message_marker(self):
        gemini = FakeGemini(
            "I will begin by reading the content of `imessage-checkin.yaml`.\nMESSAGE\nParent B: Child B pickup 5:00 PM.\nParent A: Dinner at 6:00 PM.\n\n```json\n[]\n```"
        )
        runner = RecipeRunner(self.config, gemini)
        result = runner.run_markdown_recipe(
            "imessage-checkin.yaml",
            "ctx",
            {"vault_path": str(self.root)},
            model="flash",
            approval_mode="plan",
        )
        self.assertEqual("Parent B: Child B pickup 5:00 PM.\nParent A: Dinner at 6:00 PM.", result.content)

    def test_json_plan_unwraps_gemini_outer_response(self):
        gemini = FakeGemini(json.dumps({"response": json.dumps({"reply_text": "Hi", "actions": []})}))
        runner = RecipeRunner(self.config, gemini)
        payload = runner.run_json_plan(
            "message-handler.yaml",
            "ctx",
            {"vault_path": str(self.root)},
            model="message",
            approval_mode="plan",
        )
        self.assertEqual("Hi", payload["reply_text"])
        self.assertEqual([], payload["actions"])


if __name__ == "__main__":
    unittest.main()
