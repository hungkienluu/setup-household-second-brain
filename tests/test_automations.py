from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.automations import AutomationService
from app.recipe_runner import RecipeResult

from tests.helpers import make_config, seed_vault


class FakeContexts:
    def build_daily_brief(self):
        return "ctx", "Friday, March 20, 2026"


class FakeRecipes:
    def __init__(self):
        self.calls = []

    def run_markdown_recipe(self, recipe_name, context, params, model, approval_mode, output_file=None):
        self.calls.append((recipe_name, context, params, model, approval_mode, output_file))
        if output_file is not None:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("brief body")
        return RecipeResult(content="brief body", actions=[{"action": "task", "title": "Owner A: test"}], raw_output="raw")


class FakeActions:
    def __init__(self):
        self.calls = []

    def execute_scheduled_actions(self, actions, allowed_actions):
        self.calls.append((actions, allowed_actions))


class FakeBriefs:
    def __init__(self):
        self.sent = False

    def send_current_daily_brief(self):
        self.sent = True


class AutomationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        seed_vault(self.root)
        self.config = make_config(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_daily_brief_runs_recipe_dispatches_actions_and_sends_brief(self):
        contexts = FakeContexts()
        recipes = FakeRecipes()
        actions = FakeActions()
        briefs = FakeBriefs()
        service = AutomationService(self.config, contexts, recipes, actions, briefs)

        service.daily_brief()

        self.assertEqual("daily-brief.yaml", recipes.calls[0][0])
        self.assertEqual({"task", "file_append"}, actions.calls[0][1])
        self.assertTrue(briefs.sent)


if __name__ == "__main__":
    unittest.main()
